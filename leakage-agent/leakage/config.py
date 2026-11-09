"""Detector settings. LEGACY reproduces the first version so improvements stay measurable."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    short_tol: float = 0.005          # an invoice is short if it is below expected by more than this share
    match_tol: float = 0.005          # amounts within this share of each other count as equal
    max_gap_days: int = 45            # longest normal interval between invoices (35 day cycle plus lateness)
    expansion_grace_days: int = 10    # an expansion billed within this many days is not leakage yet
    event_skew_days: int = 10         # event and invoice dates can disagree by this much (clock skew, late billing)
    handle_downgrades: bool = True    # recorded downgrades lower the expected amount
    handle_pauses: bool = True        # pause and resume events explain skipped invoices
    use_approvals: bool = True        # discounts with a matching approval are not leakage
    use_credits: bool = True          # credit memos that cover a shortfall are not leakage
    detect_proration: bool = True     # a partial first invoice after an expansion is not leakage


DEFAULT = Config()

LEGACY = Config(
    short_tol=0.005,
    match_tol=0.0,
    max_gap_days=35,
    expansion_grace_days=1,
    event_skew_days=0,
    handle_downgrades=False,
    handle_pauses=False,
    use_approvals=False,
    use_credits=False,
    detect_proration=False,
)
