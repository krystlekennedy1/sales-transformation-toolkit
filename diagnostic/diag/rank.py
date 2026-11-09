"""Rank findings by dollar impact times confidence, and attach an owner and a first fix."""
from __future__ import annotations

import pandas as pd

ACTIONS = {
    "stale_pipeline": ("Frontline manager", "low", "Hold a pipeline scrub: every untouched deal gets a dated next step or is closed out."),
    "past_due_close_dates": ("Sales operations", "low", "Add a weekly rule that flags and forces an update on any open deal with a past close date."),
    "close_date_slippage": ("Frontline manager", "medium", "Require a stated reason on every close date push and review repeat pushes in the weekly deal review."),
    "forecast_bias": ("Sales leader", "medium", "Review forecast calls against outcomes with the manager and agree on commit criteria."),
    "lead_response": ("Marketing and sales operations", "low", "Set a first-response target for this source and route new leads with an alert and an owner."),
    "discount_governance": ("Deal desk or finance", "medium", "Block quote approval above the limit until an approver is recorded."),
    "invoice_delay": ("Finance and the manager", "medium", "Trigger the invoice request automatically at closed won and track days to invoice."),
    "missing_invoice": ("Finance", "low", "Reconcile closed won deals against invoices now and bill what was missed."),
    "handoff_completeness": ("Sales operations", "low", "Make the handoff fields required before a deal can move to closed won."),
    "ramp_gap": ("Enablement and the manager", "medium", "Use the ramp coach plan for each flagged new seller and review weekly."),
}

AREA = {
    "stale_pipeline": "Pipeline", "past_due_close_dates": "Pipeline", "close_date_slippage": "Pipeline",
    "forecast_bias": "Forecast", "lead_response": "Lead to opportunity",
    "discount_governance": "Revenue protection", "invoice_delay": "Lead to cash", "missing_invoice": "Revenue protection",
    "handoff_completeness": "Lead to cash", "ramp_gap": "People and ramp",
}


def confidence(row) -> float:
    base = 0.55 + 0.40 * min(row["n"], row["n_ref"]) / row["n_ref"]
    strong = row["baseline"] <= 0 or row["value"] / row["baseline"] >= 3
    return round(min(0.95, base * (1.0 if strong else 0.85)), 2)


def rank(findings: pd.DataFrame) -> pd.DataFrame:
    f = findings.copy()
    if f.empty:
        return f.assign(area=[], confidence=[], priority_usd=[], owner=[], effort=[], first_fix=[], rank=[])
    f["area"] = f["check"].map(AREA)
    f["confidence"] = f.apply(confidence, axis=1)
    f["priority_usd"] = (f["impact_usd"] * f["confidence"]).round(2)
    f["owner"] = f["check"].map(lambda c: ACTIONS[c][0])
    f["effort"] = f["check"].map(lambda c: ACTIONS[c][1])
    f["first_fix"] = f["check"].map(lambda c: ACTIONS[c][2])
    f = f.sort_values("priority_usd", ascending=False).reset_index(drop=True)
    f["rank"] = f.index + 1
    return f
