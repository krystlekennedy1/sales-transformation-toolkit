"""Deterministic diagnosis: root cause, confidence and severity for each finding."""
from __future__ import annotations

import pandas as pd

ROOT_CAUSES = {
    "unbilled_expansion": "Expansion was contracted but billing was not updated to the new MRR.",
    "silent_discount": "Invoices run below contract price with no discount approval on record.",
    "billing_gap": "One or more invoices were never issued while the customer was still active.",
    "write_off": "Invoice was written off, so contracted revenue was not collected.",
    "unrecovered_failure": "Payment failed and was not recovered through dunning.",
}


def _confidence(row) -> float:
    ev, kind = row["evidence"], row["type"]
    if kind == "unbilled_expansion":
        return 0.95 if row["n_invoices"] >= 2 else 0.85
    if kind == "silent_discount":
        consistent = ev.get("pct_spread", 1.0) < 0.005
        if row["n_invoices"] >= 2 and consistent:
            return 0.9
        if row["n_invoices"] >= 2:
            return 0.75
        return 0.55  # one short invoice could be proration
    if kind == "billing_gap":
        return 0.65 if ev.get("near_payment_failure") else 0.85
    if kind == "write_off":
        return 0.99
    if kind == "unrecovered_failure":
        return 0.9
    return 0.5


def _severity(impact: float) -> str:
    if impact >= 10_000:
        return "high"
    if impact >= 2_000:
        return "medium"
    return "low"


def diagnose(findings: pd.DataFrame) -> pd.DataFrame:
    out = findings.copy()
    if out.empty:
        for c in ("root_cause", "confidence", "severity"):
            out[c] = []
        return out
    out["root_cause"] = out["type"].map(ROOT_CAUSES)
    out["confidence"] = out.apply(_confidence, axis=1)
    out["severity"] = out["impact_usd"].map(_severity)
    return out
