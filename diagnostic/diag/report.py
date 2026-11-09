"""Write the diagnostic as one markdown report. Draft for leadership review, synthetic data."""
from __future__ import annotations

import pandas as pd

TITLES = {
    "stale_pipeline": "Untouched pipeline", "past_due_close_dates": "Past-due close dates",
    "close_date_slippage": "Repeated close date pushes", "forecast_bias": "Forecast bias",
    "lead_response": "Slow lead response", "discount_governance": "Unapproved discounts",
    "invoice_delay": "Late invoicing", "missing_invoice": "Won deals never invoiced",
    "handoff_completeness": "Incomplete handoffs", "ramp_gap": "New sellers behind ramp",
}


def _usd(x):
    return f"${x:,.0f}"


def report(ranked: pd.DataFrame, assumptions) -> str:
    L = ["# Meridian sales organization diagnostic", "",
         "Draft for leadership review. Synthetic data for a fictional company. Dollar figures are estimates "
         "built on stated assumptions, not measured losses.", ""]
    if ranked.empty:
        return "\n".join(L + ["No findings stood out from the typical pattern.", ""])
    total = ranked["impact_usd"].sum()
    L += [f"**{len(ranked)} findings across {ranked['area'].nunique()} areas, with about {_usd(total)} of estimated impact.**", "",
          "## Fix first", "", "| # | Finding | Where | Estimated impact | Confidence | Owner | Effort |", "|---:|---|---|---:|---:|---|---|"]
    for r in ranked.head(5).itertuples():
        L.append(f"| {r.rank} | {TITLES[r.check]} | {r.entity} | {_usd(r.impact_usd)} | {r.confidence:.0%} | {r.owner} | {r.effort} |")
    L += ["", "## By area", "", "| Area | Findings | Estimated impact |", "|---|---:|---:|"]
    for area, g in ranked.groupby("area").agg(n=("check", "size"), usd=("impact_usd", "sum")).sort_values("usd", ascending=False).iterrows():
        L.append(f"| {area} | {int(g['n'])} | {_usd(g['usd'])} |")
    L += ["", "## All findings", ""]
    for r in ranked.itertuples():
        L += [f"### {r.rank}. {TITLES[r.check]}: {r.entity}", "",
              f"{r.evidence}.", "",
              f"- Estimated impact: {_usd(r.impact_usd)} ({r.basis})",
              f"- Confidence: {r.confidence:.0%} (sample of {r.n})",
              f"- Owner: {r.owner}, effort {r.effort}",
              f"- First fix: {r.first_fix}", ""]
    L += ["## Assumptions behind the dollar figures", "",
          f"- Open pipeline closes at {assumptions.win_rate:.0%}.",
          f"- A late-invoiced deal loses {assumptions.late_invoice_cost:.0%} of its value to delay and collection risk.",
          f"- Repairing one incomplete handoff takes {assumptions.rework_hours} hours at ${assumptions.hourly_cost:.0f} per hour.",
          "- Forecast error is counted in full dollars, so it is not strictly a loss.", "",
          "Impacts are in different units (lost bookings, rework cost, forecast error), so the ranking is a "
          "starting order for discussion, not a precise ordering."]
    return "\n".join(L) + "\n"
