"""Meridian ramp model. Everything here is an assumption about a fictional company, not real data.

The ramp curve is the plan: how much activity, pipeline and bookings a new seller should show by
ramp week. The coach compares each new seller to this plan and to tenured peers.
"""
from __future__ import annotations

from dataclasses import dataclass

AS_OF = "2026-11-01"

SEGMENTS = {
    "SMB": dict(quota_month=50_000.0, cycle_weeks=6, deal_size=12_000.0),
    "Mid-Market": dict(quota_month=90_000.0, cycle_weeks=10, deal_size=25_000.0),
}

MEETINGS_FULL = 8.0      # meetings held per week at full productivity
COVERAGE = 4.0           # weekly pipeline created = weekly quota x this, at full productivity
WIN_RATE = 0.25          # share of created pipeline that closes
MULTITHREAD_HEALTHY = 0.60


def ramp_pct(week: int) -> float:
    """Share of full productivity expected in a given ramp week (week 1 is the first full week)."""
    return min(1.0, 0.35 + 0.055 * max(week, 1))


def quota_week(segment: str) -> float:
    return SEGMENTS[segment]["quota_month"] * 12 / 52


def meetings_target(week: int) -> float:
    return MEETINGS_FULL * ramp_pct(week)


def pipeline_target(segment: str, week: int) -> float:
    return quota_week(segment) * COVERAGE * ramp_pct(week)


def bookings_target(segment: str, week: int) -> float:
    """Planned bookings in a ramp week: pipeline created one sales cycle earlier, times win rate."""
    src = week - SEGMENTS[segment]["cycle_weeks"]
    return WIN_RATE * pipeline_target(segment, src) if src >= 1 else 0.0


@dataclass(frozen=True)
class Thresholds:
    at_risk: float = 0.75      # a leading indicator below this share of plan is a problem
    watch: float = 0.90        # below this share of plan is worth watching
    mt_low: float = 0.35       # share of opportunities with 2+ contacts, below this is single threaded
    window: int = 4            # weeks used for leading indicators
    min_week: int = 4          # no judgement before this ramp week
    book_wait: int = 4         # weeks past one sales cycle before bookings are judged
    book_low: float = 0.70     # cumulative bookings below this share of plan is a conversion problem
