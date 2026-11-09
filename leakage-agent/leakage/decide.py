"""Decision matrix: finding type to recommended strategy, then guardrails decide what happens."""
from __future__ import annotations

import pandas as pd

from .audit import AuditLog
from .guardrails import DRAFT_ONLY, Limits, evaluate

STRATEGY = {
    "unbilled_expansion": "request_correction_invoice",
    "silent_discount": "route_to_deal_desk",
    "billing_gap": "request_backbill",
    "write_off": "escalate_human",
    "unrecovered_failure": "draft_dunning_outreach",
}


def decide(findings: pd.DataFrame, limits: Limits, audit: AuditLog) -> pd.DataFrame:
    assert DRAFT_ONLY, "this prototype must never execute actions"
    out = findings.sort_values("impact_usd", ascending=False).copy()
    recent = audit.recent_actions(limits.cooldown_days)
    drafts = 0
    strategies, statuses, reasons = [], [], []
    for _, row in out.iterrows():
        strategy = STRATEGY[row["type"]]
        status, reason = evaluate(row, limits, strategy, drafts, recent)
        if status == "drafted":
            drafts += 1
        strategies.append(strategy)
        statuses.append(status)
        reasons.append(reason)
        audit.record(row["finding_id"], "decide", status=status, strategy=strategy, reason=reason,
                     impact_usd=round(float(row["impact_usd"]), 2), confidence=float(row["confidence"]))
    out["strategy"] = strategies
    out["status"] = statuses
    out["reason"] = reasons
    return out.reset_index(drop=True)
