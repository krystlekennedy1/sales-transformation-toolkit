"""Explanation layer.

The rule engine always runs first and owns every number, action and guardrail. This layer may
only rewrite two pieces of text: the explanation and the suggested next step. If no API key is
set, the SDK is missing, the call fails, the reply is malformed, or the reply cites a dollar
amount that is not in the finding, the rule-based text is used instead.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

DEFAULT_MODEL = os.environ.get("LEAKAGE_MODEL", "claude-sonnet-5-5")

SYSTEM = (
    "You review revenue leakage findings found in synthetic billing data. A rule engine has already "
    "decided the action. Write a plain-English explanation and one next step for a sales operations "
    "lead. Do not change or invent any amount. Do not propose discounts, credits or direct customer "
    "contact. Do not use em dashes. Reply with JSON only, in this shape: "
    '{"explanation": "<1 to 3 sentences>", "next_step": "<1 sentence>"}'
)


@dataclass
class Explanation:
    explanation: str
    next_step: str
    source: str  # "rules" or "claude"


def rule_based(row, company: str) -> Explanation:
    ev, impact, n = row["evidence"], row["impact_usd"], int(row["n_invoices"])
    kind = row["type"]
    if kind == "unbilled_expansion":
        return Explanation(
            f"{company} expanded to ${ev['expected_amount']:,.0f} per month on {ev['step_date']}, but {n} "
            f"invoice(s) since were billed at ${ev['billed_amount']:,.0f}. About ${impact:,.0f} has not been billed.",
            "Ask billing ops to confirm the expansion order and issue a correction invoice.",
            "rules",
        )
    if kind == "silent_discount":
        return Explanation(
            f"{company} has been invoiced about {ev['avg_shortfall_pct']:.0%} below contract price on {n} "
            f"invoice(s), with no discount approval on record. About ${impact:,.0f} is affected.",
            "Ask the deal desk whether a discount was approved. If not, bill the difference.",
            "rules",
        )
    if kind == "billing_gap":
        if ev.get("trailing"):
            text = (f"Billing for {company} stopped {ev['gap_days']} days before the data cutoff and the customer "
                    f"has not churned. About {ev['missing_invoices']} invoice(s), roughly ${impact:,.0f}, are missing.")
        else:
            text = (f"{company} went {ev['gap_days']} days between invoices, so about {ev['missing_invoices']} "
                    f"invoice(s) were never issued, worth roughly ${impact:,.0f}.")
        return Explanation(text, "Ask billing ops whether the invoices were skipped, and back-bill if so.", "rules")
    if kind == "write_off":
        return Explanation(
            f"{n} invoice(s) for {company} totaling ${impact:,.0f} were written off.",
            "Review the write-off approval and decide whether collection should be retried.",
            "rules",
        )
    return Explanation(
        f"A payment from {company} failed and was never recovered, leaving ${impact:,.0f} uncollected.",
        "Prepare a dunning follow-up for a human to review and send.",
        "rules",
    )


def make_client():
    """Return an Anthropic client, or None if there is no key or the SDK is not installed."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.Anthropic()


def _numbers_in(text: str) -> set[float]:
    return {float(m.replace(",", "")) for m in re.findall(r"\d[\d,]*\.?\d*", text) if m.replace(",", "").replace(".", "").isdigit()}


def _amounts_ok(reply: str, allowed: set[float]) -> bool:
    for raw in re.findall(r"\$([\d,]+(?:\.\d+)?)", reply):
        amount = float(raw.replace(",", ""))
        if not any(abs(amount - a) <= max(1.0, 0.01 * a) for a in allowed):
            return False
    return True


def _clean(text: str) -> str:
    dash = chr(0x2014)  # em dash, written as a code point to keep this source file clean
    return text.replace(f" {dash} ", ", ").replace(dash, "-").strip()


class Explainer:
    def __init__(self, client=None, model: str = DEFAULT_MODEL):
        self.client = client
        self.model = model

    def explain(self, row, company: str) -> Explanation:
        base = rule_based(row, company)
        if self.client is None:
            return base
        facts = {
            "company": company,
            "finding_type": row["type"],
            "impact_usd": round(float(row["impact_usd"]), 2),
            "invoices_affected": int(row["n_invoices"]),
            "root_cause": row["root_cause"],
            "evidence": row["evidence"],
            "recommended_action": row.get("strategy"),
        }
        facts_json = json.dumps(facts, default=str)
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=400,
                system=SYSTEM,
                messages=[{"role": "user", "content": facts_json}],
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
            data = json.loads(text[text.index("{"): text.rindex("}") + 1])
            explanation, next_step = _clean(data["explanation"]), _clean(data["next_step"])
            if not (10 <= len(explanation) <= 600 and 5 <= len(next_step) <= 300):
                return base
            if not _amounts_ok(explanation + " " + next_step, _numbers_in(facts_json)):
                return base
            return Explanation(explanation, next_step, "claude")
        except Exception:
            return base
