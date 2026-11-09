"""Hard limits applied after diagnosis and after any AI step.

Nothing in this prototype executes an action. Every action is a draft for a human to review,
and DRAFT_ONLY is asserted in the decision step.
"""
from __future__ import annotations

from dataclasses import dataclass

DRAFT_ONLY = True


@dataclass(frozen=True)
class Limits:
    min_impact_usd: float = 100.0          # below this, suppress as immaterial
    confidence_floor: float = 0.60         # below this, send to human review with no draft
    escalate_above_usd: float = 25_000.0   # at or above this, a human must own it
    max_drafts_per_run: int = 50           # budget on drafts in a single run
    cooldown_days: int = 14                # no repeat draft for the same finding inside this window


def evaluate(row, limits: Limits, strategy: str, drafts_so_far: int, recent: set[str]) -> tuple[str, str]:
    """Return (status, reason). The first rule that fires wins."""
    if row["impact_usd"] < limits.min_impact_usd:
        return "suppressed", f"below materiality threshold of ${limits.min_impact_usd:,.0f}"
    if row["finding_id"] in recent:
        return "suppressed", f"already actioned within the last {limits.cooldown_days} days"
    if row["confidence"] < limits.confidence_floor:
        return "needs_review", f"confidence {row['confidence']:.2f} is below the {limits.confidence_floor:.2f} floor"
    if strategy == "escalate_human":
        return "escalated", "policy: this finding type always needs a human decision"
    if row["impact_usd"] >= limits.escalate_above_usd:
        return "escalated", f"impact is at or above ${limits.escalate_above_usd:,.0f}"
    if drafts_so_far >= limits.max_drafts_per_run:
        return "deferred", f"draft budget of {limits.max_drafts_per_run} per run reached"
    return "drafted", "within limits"
