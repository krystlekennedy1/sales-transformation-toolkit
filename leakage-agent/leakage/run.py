"""Run the agent end to end: detect, diagnose, decide with guardrails, draft, audit, score.

    python -m leakage.run --data data/injected --out output --fresh
    python -m leakage.run --data data/injected --out output --fresh --ai   # Claude explanations
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

from .agent import Explainer, make_client
from .audit import AuditLog
from .decide import decide
from .config import DEFAULT, LEGACY, Config
from .detect import detect_all
from .diagnose import diagnose
from .drafts import write_draft
from .expected import attach_expected, load_tables, mrr_steps
from .guardrails import Limits
from .score import score


def run(data_dir, out_dir, truth_path=None, use_ai=False, limits: Limits | None = None, fresh=False,
        cfg: Config = DEFAULT):
    limits = limits or Limits()
    out = Path(out_dir)
    if fresh and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(out / "audit.jsonl")

    t = load_tables(data_dir)
    inv_exp = attach_expected(t["invoices"], mrr_steps(t["customers"], t["subscription_events"], cfg))
    as_of = inv_exp["invoice_date"].max()
    names = t["customers"].merge(t["accounts"][["account_id", "company_name"]], on="account_id")
    company = dict(zip(names["customer_id"], names["company_name"]))

    findings = detect_all(inv_exp, t["subscription_events"], as_of, cfg, t["discount_approvals"], t["credit_memos"])
    for _, r in findings.iterrows():
        audit.record(r["finding_id"], "detect", type=r["type"], impact_usd=round(float(r["impact_usd"]), 2))
    findings = diagnose(findings)
    for _, r in findings.iterrows():
        audit.record(r["finding_id"], "diagnose", confidence=float(r["confidence"]), severity=r["severity"])
    decisions = decide(findings, limits, audit)

    explainer = Explainer(client=make_client() if use_ai else None)
    if use_ai and explainer.client is None:
        print("note: --ai was set but no ANTHROPIC_API_KEY or SDK was found, using rule-based text")
    texts = {}
    for _, r in decisions[decisions["status"].isin(["drafted", "escalated"])].iterrows():
        name = company.get(r["customer_id"], r["customer_id"])
        texts[r["finding_id"]] = explainer.explain(r, name)
        write_draft(out / "drafts", r, name, texts[r["finding_id"]])
        audit.record(r["finding_id"], "explain", source=texts[r["finding_id"]].source)

    decisions["company"] = decisions["customer_id"].map(company)
    decisions["explanation"] = decisions["finding_id"].map(lambda i: texts[i].explanation if i in texts else "")
    decisions["next_step"] = decisions["finding_id"].map(lambda i: texts[i].next_step if i in texts else "")
    decisions["explanation_source"] = decisions["finding_id"].map(lambda i: texts[i].source if i in texts else "")
    decisions["evidence"] = decisions["evidence"].map(lambda e: json.dumps(e, default=str))
    decisions.to_csv(out / "findings.csv", index=False)

    scores = None
    if truth_path and Path(truth_path).exists():
        scores = score(decisions, pd.read_csv(truth_path))
    summary = build_summary(decisions, scores, as_of)
    (out / "summary.md").write_text(summary)
    return decisions, scores, summary


def build_summary(d: pd.DataFrame, scores, as_of) -> str:
    lines = [f"# Revenue leakage run (synthetic data, as of {as_of:%Y-%m-%d})", ""]
    lines.append(f"Findings: {len(d)}. Estimated impact: ${d['impact_usd'].sum():,.0f}.")
    lines += ["", "## By type", "", "| Type | Findings | Impact (USD) |", "|---|---:|---:|"]
    for kind, g in d.groupby("type"):
        lines.append(f"| {kind} | {len(g)} | {g['impact_usd'].sum():,.0f} |")
    lines += ["", "## By guardrail outcome", "", "| Status | Findings | Impact (USD) |", "|---|---:|---:|"]
    for status, g in d.groupby("status"):
        lines.append(f"| {status} | {len(g)} | {g['impact_usd'].sum():,.0f} |")
    lines += ["", "## Top 10 by impact", "", "| Customer | Type | Impact (USD) | Status |", "|---|---|---:|---|"]
    for _, r in d.head(10).iterrows():
        lines.append(f"| {r['company']} | {r['type']} | {r['impact_usd']:,.0f} | {r['status']} |")
    if scores is not None:
        lines += ["", "## Score against planted leakage", "",
                  "| Type | Planted | Flagged | Correct | Precision | Recall | Planted USD | Estimated USD |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for _, s in scores.iterrows():
            lines.append(f"| {s['type']} | {s['planted']} | {s['flagged']} | {s['correct']} | {s['precision']:.0%} | "
                         f"{s['recall']:.0%} | {s['planted_usd']:,} | {s['estimated_usd']:,} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default="data/injected")
    p.add_argument("--out", default="output")
    p.add_argument("--truth", default=None, help="ground_truth.csv, defaults to <data>/ground_truth.csv if present")
    p.add_argument("--ai", action="store_true", help="use Claude for explanations (needs ANTHROPIC_API_KEY)")
    p.add_argument("--legacy", action="store_true", help="use the first-version detector settings")
    p.add_argument("--fresh", action="store_true", help="clear the output folder first, including the audit log")
    a = p.parse_args()
    truth = a.truth or str(Path(a.data) / "ground_truth.csv")
    _, _, summary = run(a.data, a.out, truth, use_ai=a.ai, fresh=a.fresh,
                         cfg=LEGACY if a.legacy else DEFAULT)
    print(summary)


if __name__ == "__main__":
    main()
