"""Evaluate detectors on a dataset that has planted leakage and, optionally, planted noise.

Reports precision and recall per leakage type, and traces every false positive to its cause so
it is clear which kind of noise is fooling a detector. Native write-offs and payment failures from
the data generator are real findings and are left out of the score.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from .audit import AuditLog
from .config import DEFAULT, Config
from .decide import decide
from .detect import detect_all
from .diagnose import diagnose
from .expected import attach_expected, load_tables, mrr_steps
from .guardrails import Limits
from .score import INJECTED_TYPES, score


def false_positives(decisions: pd.DataFrame, truth: pd.DataFrame, noise_truth: pd.DataFrame) -> pd.DataFrame:
    planted = set(zip(truth["type"], truth["customer_id"]))
    planted_types = truth.groupby("customer_id")["type"].agg(lambda s: ", ".join(sorted(set(s)))).to_dict()
    noise_kind = dict(zip(noise_truth["customer_id"], noise_truth["kind"]))
    rows = []
    for r in decisions[decisions["type"].isin(INJECTED_TYPES)].itertuples():
        if (r.type, r.customer_id) in planted:
            continue
        if r.customer_id in planted_types:
            cause = f"type confusion (planted {planted_types[r.customer_id]})"
        elif r.customer_id in noise_kind:
            cause = noise_kind[r.customer_id]
        else:
            cause = "unexplained (late invoices or rounding)"
        rows.append(dict(cause=cause, flagged_as=r.type, status=r.status, impact_usd=r.impact_usd))
    return pd.DataFrame(rows, columns=["cause", "flagged_as", "status", "impact_usd"])


def evaluate(data_dir, cfg: Config = DEFAULT, transform=None):
    """transform, if given, edits the loaded tables first (used to simulate missing records)."""
    d = Path(data_dir)
    t = load_tables(d)
    if transform is not None:
        t = transform(t)
    inv_exp = attach_expected(t["invoices"], mrr_steps(t["customers"], t["subscription_events"], cfg))
    found = detect_all(inv_exp, t["subscription_events"], inv_exp["invoice_date"].max(), cfg,
                       t["discount_approvals"], t["credit_memos"])
    with tempfile.TemporaryDirectory() as tmp:
        decisions = decide(diagnose(found), Limits(), AuditLog(Path(tmp) / "audit.jsonl"))
    truth = pd.read_csv(d / "ground_truth.csv")
    noise_path = d / "noise_truth.csv"
    noise_truth = pd.read_csv(noise_path) if noise_path.exists() else pd.DataFrame(columns=["kind", "customer_id", "detail"])
    return score(decisions, truth), false_positives(decisions, truth, noise_truth), decisions


def report(name: str, scores: pd.DataFrame, fps: pd.DataFrame) -> str:
    lines = [f"### {name}", "", "| Type | Planted | Flagged | Correct | Precision | Recall | $ accuracy |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for _, s in scores.iterrows():
        lines.append(f"| {s['type']} | {s['planted']} | {s['flagged']} | {s['correct']} | {s['precision']:.0%} | "
                     f"{s['recall']:.0%} | {s['dollar_accuracy']:.0%} |")
    lines += ["", f"False positives: {len(fps)}"]
    if len(fps):
        lines += ["", "| Cause | Flagged as | Count | Reached a draft or escalation |", "|---|---|---:|---:|"]
        g = fps.groupby(["cause", "flagged_as"]).agg(n=("status", "size"),
                                                      acted=("status", lambda s: s.isin(["drafted", "escalated"]).sum()))
        for (cause, flagged), r in g.sort_values("n", ascending=False).iterrows():
            lines.append(f"| {cause} | {flagged} | {r['n']} | {r['acted']} |")
    return "\n".join(lines) + "\n"
