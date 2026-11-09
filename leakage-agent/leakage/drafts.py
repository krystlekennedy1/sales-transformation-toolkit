"""Draft-only outputs. Each draft is a markdown file for a human to review. Nothing is sent."""
from __future__ import annotations

import re
from pathlib import Path

TITLES = {
    "request_correction_invoice": "Request a correction invoice",
    "route_to_deal_desk": "Review a possible unapproved discount",
    "request_backbill": "Request back-billing for missed invoices",
    "escalate_human": "Escalation: needs a human decision",
    "draft_dunning_outreach": "Dunning follow-up",
}


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)


def write_draft(directory, row, company: str, explanation) -> Path:
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    evidence = "\n".join(f"- {k}: {v}" for k, v in row["evidence"].items())
    body = f"""# Draft: {TITLES[row['strategy']]}

**Status: DRAFT ONLY. Nothing has been sent, billed or changed.**

| | |
|---|---|
| Customer | {company} ({row['customer_id']}) |
| Finding | {row['finding_id']} |
| Type | {row['type']} |
| Estimated revenue impact | ${row['impact_usd']:,.0f} |
| Period | {row['first_date']:%Y-%m-%d} to {row['last_date']:%Y-%m-%d} |
| Confidence | {row['confidence']:.0%} |
| Guardrail result | {row['status']}: {row['reason']} |

## What we see
{explanation.explanation}

## Suggested next step
{explanation.next_step}

## Evidence
{evidence}

_Explanation source: {explanation.source}. Data is synthetic._
"""
    path = d / f"{_slug(row['finding_id'])}.md"
    path.write_text(body)
    return path
