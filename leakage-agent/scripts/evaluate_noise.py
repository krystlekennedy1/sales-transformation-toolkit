"""Evaluate the detectors on noisy data and write NOISE_REPORT.md.

Sections: before and after on the tuning set (A) and the holdout set (B), an ablation that turns
each fix off, a missing-records scenario, and checks on the original no-noise datasets.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from leakage.config import DEFAULT, LEGACY  # noqa: E402
from leakage.evaluate import evaluate, report  # noqa: E402
from leakage.expected import attach_expected, load_tables, mrr_steps  # noqa: E402
from leakage.detect import detect_all  # noqa: E402

TYPES = ["unbilled_expansion", "silent_discount", "billing_gap"]


def short(name, s, fp, d):
    s = s.set_index("type")
    cells = [f"{s.loc[t, 'precision']:.0%} / {s.loc[t, 'recall']:.0%}" for t in TYPES]
    acted = int(fp["status"].isin(["drafted", "escalated"]).sum()) if len(fp) else 0
    return f"| {name} | {len(fp)} | {acted} | " + " | ".join(cells) + " |"


HEADER = ("| Variant | False positives | Reached a draft or escalation | Unbilled expansion (P / R) | "
          "Silent discount (P / R) | Billing gap (P / R) |\n|---|---:|---:|---|---|---|")


def drop_half_of_records(t):
    rng = np.random.default_rng(5)
    t = dict(t)
    for k in ("discount_approvals", "credit_memos"):
        keep = rng.random(len(t[k])) < 0.5
        t[k] = t[k][keep].reset_index(drop=True)
    return t


def main() -> None:
    out = ["# Noise evaluation", "",
           "P is precision and R is recall, against leakage planted in each dataset. A false positive is a "
           "finding of a planted type on a customer that has no such planted leakage. Native write-offs from the "
           "data generator are real and are excluded. Set A was used to tune the detectors. Set B was scored "
           "once the detectors were final.", ""]

    out += ["## Before and after", "", HEADER]
    for name in ("noisy_a", "noisy_b"):
        for label, cfg in (("first version", LEGACY), ("improved", DEFAULT)):
            out.append(short(f"{name}, {label}", *evaluate(ROOT / "data" / name, cfg)))
    out.append("")

    for name in ("noisy_a", "noisy_b"):
        for label, cfg in (("first version", LEGACY), ("improved", DEFAULT)):
            s, fp, _ = evaluate(ROOT / "data" / name, cfg)
            out.append(report(f"{name}, {label}", s, fp))

    out += ["## Ablation on holdout set B", "",
            "Each row turns off one improvement and leaves the rest on.", "", HEADER]
    variants = {
        "all improvements": DEFAULT,
        "no lateness tolerance (35 day gap limit)": replace(DEFAULT, max_gap_days=35),
        "no expansion grace period": replace(DEFAULT, expansion_grace_days=1),
        "no amount tolerance when classifying": replace(DEFAULT, match_tol=0.0),
        "no downgrade handling": replace(DEFAULT, handle_downgrades=False),
        "no pause handling": replace(DEFAULT, handle_pauses=False),
        "no proration rule": replace(DEFAULT, detect_proration=False),
        "no approvals table": replace(DEFAULT, use_approvals=False),
        "no credit memo table": replace(DEFAULT, use_credits=False),
        "no event skew tolerance": replace(DEFAULT, event_skew_days=0),
    }
    for label, cfg in variants.items():
        out.append(short(label, *evaluate(ROOT / "data" / "noisy_b", cfg)))
    out.append("")

    out += ["## Missing records on holdout set B", "",
            "Half of the discount approval and credit memo records are removed, as in real data where "
            "approvals and credits are not always logged.", "", HEADER]
    s, fp, d = evaluate(ROOT / "data" / "noisy_b", DEFAULT, transform=drop_half_of_records)
    out.append(short("improved, half of records missing", s, fp, d))
    out.append("")
    if len(fp):
        by = fp.groupby(["cause", "status"]).size().rename("n").reset_index().sort_values("n", ascending=False)
        out += ["| Cause | Guardrail outcome | Count |", "|---|---|---:|"]
        out += [f"| {r.cause} | {r.status} | {r.n} |" for r in by.itertuples()]
        out.append("")

    out += ["## Original datasets without noise", "", HEADER]
    out.append(short("injected only, first version", *evaluate(ROOT / "data" / "injected", LEGACY)))
    out.append(short("injected only, improved", *evaluate(ROOT / "data" / "injected", DEFAULT)))
    t = load_tables(ROOT / "data" / "clean")
    ie = attach_expected(t["invoices"], mrr_steps(t["customers"], t["subscription_events"], DEFAULT))
    f = detect_all(ie, t["subscription_events"], ie["invoice_date"].max(), DEFAULT)
    out += ["", f"Clean data with no planted leakage, improved detectors: {f['type'].value_counts().to_dict()}", ""]

    text = "\n".join(out)
    (ROOT / "NOISE_REPORT.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
