"""Assumptions behind the dollar estimates. These are guesses about a fictional company.

Change them to match a real business before trusting any ranking. scripts/evaluate.py shows how much
the ranking moves when they change.
"""
from __future__ import annotations

from dataclasses import dataclass

AS_OF = "2026-11-01"


@dataclass(frozen=True)
class Assumptions:
    win_rate: float = 0.25          # share of open pipeline that eventually closes
    late_invoice_cost: float = 0.05  # share of a late-invoiced deal's value lost to delay and collection risk
    rework_hours: float = 1.5       # hours to repair one incomplete handoff
    hourly_cost: float = 75.0       # loaded cost of an hour of ops or finance time
    stale_days: int = 30            # no activity for this long makes an open deal stale
    ratio: float = 2.0              # an entity must be this many times the typical entity to be flagged
    discount_limit: float = 0.15    # discounts above this need approval


DEFAULT = Assumptions()
