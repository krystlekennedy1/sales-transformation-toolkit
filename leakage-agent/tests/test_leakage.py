import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from leakage.agent import Explainer, rule_based
from leakage.config import DEFAULT
from leakage.audit import AuditLog
from leakage.decide import STRATEGY, decide
from leakage.detect import detect_billing_gaps, detect_underbilling, detect_write_offs
from leakage.diagnose import diagnose
from leakage.expected import attach_expected, load_tables, mrr_steps
from leakage.guardrails import DRAFT_ONLY, Limits
from leakage.score import score

ROOT = Path(__file__).resolve().parent.parent


DASH = chr(0x2014)


def D(s):
    return pd.Timestamp(s)


def customers(*rows):
    return pd.DataFrame(rows, columns=["customer_id", "customer_start_at", "initial_mrr"]).assign(
        customer_start_at=lambda d: pd.to_datetime(d["customer_start_at"])
    )


def events(*rows):
    df = pd.DataFrame(rows, columns=["customer_id", "event_timestamp", "event_type", "mrr_before", "mrr_after"])
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
    return df


def invoices(*rows):
    df = pd.DataFrame(rows, columns=["invoice_id", "customer_id", "invoice_date", "amount_usd", "payment_status"])
    df["invoice_date"] = pd.to_datetime(df["invoice_date"])
    return df


def weekly(cust, start, amounts, step=28, prefix="i"):
    d = D(start)
    rows = []
    for k, a in enumerate(amounts):
        rows.append((f"{prefix}{cust}{k}", cust, d + timedelta(days=step * k), a, "paid"))
    return rows


def build(cust_rows, ev_rows, inv_rows):
    steps = mrr_steps(customers(*cust_rows), events(*ev_rows) if ev_rows else events())
    return attach_expected(invoices(*inv_rows), steps)


# ---------- expected billing ----------

def test_change_on_invoice_date_applies_to_next_invoice():
    ie = build(
        [("c1", "2024-01-01", 1000)],
        [("c1", "2024-03-01", "expansion", 1000, 1500)],
        [("a", "c1", "2024-02-01", 1000, "paid"), ("b", "c1", "2024-03-01", 1000, "paid"),
         ("c", "c1", "2024-03-29", 1500, "paid")],
    )
    assert ie["expected_amount"].tolist() == [1000, 1000, 1500]
    assert detect_underbilling(ie).empty


def test_first_invoice_on_start_date_is_matched():
    ie = build([("c1", "2024-01-01", 1000)], [], [("a", "c1", "2024-01-01", 1000, "paid")])
    assert ie["expected_amount"].tolist() == [1000]


# ---------- underbilling ----------

def test_unbilled_expansion_detected_with_exact_impact():
    ie = build(
        [("c1", "2024-01-01", 1000)],
        [("c1", "2024-02-10", "expansion", 1000, 1600)],
        [("a", "c1", "2024-01-01", 1000, "paid"), ("b", "c1", "2024-01-29", 1000, "paid"),
         ("c", "c1", "2024-02-26", 1000, "paid"), ("d", "c1", "2024-03-25", 1000, "paid")],
    )
    f = detect_underbilling(ie)
    assert len(f) == 1
    row = f.iloc[0]
    assert row["type"] == "unbilled_expansion"
    assert row["n_invoices"] == 2 and row["impact_usd"] == 1200
    assert row["evidence"]["step_date"] == "2024-02-10"


def test_silent_discount_detected_and_not_confused_with_expansion():
    ie = build(
        [("c1", "2024-01-01", 1000)],
        [],
        weekly("c1", "2024-01-01", [1000, 900, 900, 900]),
    )
    f = detect_underbilling(ie)
    assert len(f) == 1 and f.iloc[0]["type"] == "silent_discount"
    assert f.iloc[0]["impact_usd"] == 300
    assert f.iloc[0]["evidence"]["avg_shortfall_pct"] == 0.1


def test_tiny_rounding_difference_is_ignored():
    ie = build([("c1", "2024-01-01", 1000)], [], weekly("c1", "2024-01-01", [1000, 999.99, 1000]))
    assert detect_underbilling(ie).empty


# ---------- billing gaps ----------

def test_normal_28_and_35_day_cycles_are_not_gaps():
    rows = [("a", "c1", "2024-01-01", 1000, "paid"), ("b", "c1", "2024-01-29", 1000, "paid"),
            ("c", "c1", "2024-03-04", 1000, "paid")]  # 28 then 35 days
    ie = build([("c1", "2024-01-01", 1000)], [], rows)
    assert detect_billing_gaps(ie, events(), D("2024-03-10")).empty


def test_one_and_two_missing_invoices_are_counted():
    one = [("a", "c1", "2024-01-01", 1000, "paid"), ("b", "c1", "2024-02-26", 1000, "paid")]  # 56 days
    two = [("a", "c2", "2024-01-01", 500, "paid"), ("b", "c2", "2024-03-25", 500, "paid")]  # 84 days
    ie = build([("c1", "2024-01-01", 1000), ("c2", "2024-01-01", 500)], [], one + two)
    f = detect_billing_gaps(ie, events(), D("2024-03-26")).set_index("customer_id")
    assert f.loc["c1", "n_invoices"] == 1 and f.loc["c1", "impact_usd"] == 1000
    assert f.loc["c2", "n_invoices"] == 2 and f.loc["c2", "impact_usd"] == 1000


def test_billing_that_stopped_is_flagged_unless_customer_churned():
    rows = [("a", "c1", "2024-01-01", 1000, "paid"), ("b", "c2", "2024-01-01", 1000, "paid")]
    ie = build([("c1", "2024-01-01", 1000), ("c2", "2024-01-01", 1000)],
               [("c2", "2024-01-20", "churn", 1000, 0)], rows)
    f = detect_billing_gaps(ie, events(("c2", "2024-01-20", "churn", 1000, 0)), D("2024-04-01"))
    assert f["customer_id"].tolist() == ["c1"]
    assert f.iloc[0]["evidence"]["trailing"] is True


def test_gap_near_payment_failure_gets_lower_confidence():
    rows = [("a", "c1", "2024-01-01", 1000, "paid"), ("b", "c1", "2024-02-26", 1000, "paid"),
            ("c", "c2", "2024-01-01", 1000, "paid"), ("d", "c2", "2024-02-26", 1000, "paid")]
    ev = events(("c1", "2024-01-20", "payment_failure", 1000, 1000))
    ie = build([("c1", "2024-01-01", 1000), ("c2", "2024-01-01", 1000)], [], rows)
    f = diagnose(detect_billing_gaps(ie, ev, D("2024-03-01"))).set_index("customer_id")
    assert f.loc["c1", "confidence"] < f.loc["c2", "confidence"]


# ---------- write offs ----------

def test_write_off_and_unrecovered_failure_are_reported():
    rows = [("a", "c1", "2024-01-01", 400, "written_off"), ("b", "c1", "2024-01-29", 400, "paid"),
            ("c", "c2", "2024-01-01", 250, "failed")]
    ie = build([("c1", "2024-01-01", 400), ("c2", "2024-01-01", 250)], [], rows)
    f = detect_write_offs(ie).set_index("type")
    assert f.loc["write_off", "impact_usd"] == 400
    assert f.loc["unrecovered_failure", "impact_usd"] == 250


# ---------- guardrails and decisions ----------

def finding(fid, kind, impact, confidence=0.9):
    evidence = {"gap_days": 60, "missing_invoices": 1, "trailing": False, "avg_shortfall_pct": 0.1,
                "expected_amount": 1000.0, "billed_amount": 900.0, "step_date": "2024-01-01"}
    return dict(finding_id=fid, customer_id=fid, type=kind, first_date=D("2024-01-01"), last_date=D("2024-02-01"),
                n_invoices=1, impact_usd=impact, evidence=evidence, root_cause="x", confidence=confidence,
                severity="low")


def decide_one(tmp_path, rows, limits=None, audit=None):
    audit = audit or AuditLog(tmp_path / "audit.jsonl")
    return decide(pd.DataFrame(rows), limits or Limits(), audit).set_index("finding_id")


def test_each_guardrail_branch(tmp_path):
    d = decide_one(tmp_path, [
        finding("tiny", "billing_gap", 50),
        finding("unsure", "silent_discount", 5_000, confidence=0.55),
        finding("huge", "unbilled_expansion", 30_000),
        finding("woff", "write_off", 2_000, confidence=0.99),
        finding("ok", "billing_gap", 2_000),
    ])
    assert d.loc["tiny", "status"] == "suppressed"
    assert d.loc["unsure", "status"] == "needs_review"
    assert d.loc["huge", "status"] == "escalated"
    assert d.loc["woff", "status"] == "escalated"  # policy, regardless of size
    assert d.loc["ok", "status"] == "drafted"


def test_materiality_check_runs_before_confidence(tmp_path):
    d = decide_one(tmp_path, [finding("x", "silent_discount", 10, confidence=0.1)])
    assert d.loc["x", "status"] == "suppressed"


def test_draft_budget_defers_the_smaller_findings(tmp_path):
    rows = [finding(f"f{i}", "billing_gap", 1_000 + i) for i in range(5)]
    d = decide_one(tmp_path, rows, Limits(max_drafts_per_run=2))
    assert (d["status"] == "drafted").sum() == 2
    assert (d["status"] == "deferred").sum() == 3
    # highest impact is handled first
    assert d.loc["f4", "status"] == "drafted" and d.loc["f0", "status"] == "deferred"


def test_cooldown_suppresses_repeat_actions(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    first = decide_one(tmp_path, [finding("a", "billing_gap", 2_000)], audit=audit)
    assert first.loc["a", "status"] == "drafted"
    second = decide_one(tmp_path, [finding("a", "billing_gap", 2_000)], audit=audit)
    assert second.loc["a", "status"] == "suppressed"
    assert "already actioned" in second.loc["a", "reason"]


def test_old_actions_do_not_trigger_cooldown(tmp_path):
    path = tmp_path / "audit.jsonl"
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    path.write_text(json.dumps({"ts": old, "finding_id": "a", "step": "decide", "status": "drafted"}) + "\n")
    d = decide_one(tmp_path, [finding("a", "billing_gap", 2_000)], audit=AuditLog(path))
    assert d.loc["a", "status"] == "drafted"


def test_every_decision_is_audited_and_draft_only(tmp_path):
    assert DRAFT_ONLY is True
    audit = AuditLog(tmp_path / "audit.jsonl")
    decide_one(tmp_path, [finding("a", "billing_gap", 2_000), finding("b", "write_off", 500)], audit=audit)
    steps = [(e["finding_id"], e["step"]) for e in audit.entries()]
    assert ("a", "decide") in steps and ("b", "decide") in steps
    assert set(STRATEGY) == {"unbilled_expansion", "silent_discount", "billing_gap", "write_off",
                             "unrecovered_failure"}


# ---------- Claude explanation layer ----------

class Stub:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc = reply, exc
        self.messages = self

    def create(self, **kwargs):
        if self.exc:
            raise self.exc
        block = type("B", (), {"type": "text", "text": self.reply})
        return type("R", (), {"content": [block]})


ROW = {"type": "unbilled_expansion", "impact_usd": 12_345.0, "n_invoices": 3, "root_cause": "rc",
       "evidence": {"expected_amount": 5000.0, "billed_amount": 3000.0, "step_date": "2024-05-01"},
       "strategy": "request_correction_invoice"}


def test_no_client_uses_rule_text():
    e = Explainer(client=None).explain(ROW, "Acme")
    assert e.source == "rules" and "$12,345" in e.explanation


def test_valid_claude_reply_is_used():
    reply = json.dumps({"explanation": "Acme was billed $3,000 instead of $5,000 for three cycles.",
                        "next_step": "Ask billing ops to confirm the expansion."})
    e = Explainer(client=Stub(reply)).explain(ROW, "Acme")
    assert e.source == "claude" and "$3,000" in e.explanation


@pytest.mark.parametrize("reply", [
    json.dumps({"explanation": "Acme owes $99,999 in unbilled revenue.", "next_step": "Call the customer today."}),
    "not json at all",
    json.dumps({"explanation": "short", "next_step": "x"}),
    json.dumps({"explanation": "Missing the next step key entirely here."}),
])
def test_bad_claude_replies_fall_back_to_rules(reply):
    assert Explainer(client=Stub(reply)).explain(ROW, "Acme").source == "rules"


def test_api_error_falls_back_to_rules():
    assert Explainer(client=Stub(exc=RuntimeError("boom"))).explain(ROW, "Acme").source == "rules"


def test_em_dashes_are_removed_from_claude_text():
    reply = json.dumps({"explanation": f"Acme was under billed {DASH} for three cycles in a row.",
                        "next_step": f"Ask billing ops to confirm {DASH} then correct it."})
    e = Explainer(client=Stub(reply)).explain(ROW, "Acme")
    assert DASH not in e.explanation + e.next_step


def test_claude_cannot_change_the_decision(tmp_path):
    findings = pd.DataFrame([finding("a", "billing_gap", 2_000)])
    before = decide(findings, Limits(), AuditLog(tmp_path / "a.jsonl"))
    reply = json.dumps({"explanation": "Escalate this immediately please.", "next_step": "Waive everything now."})
    row = before.iloc[0]
    Explainer(client=Stub(reply)).explain(row, "Acme")
    assert before.iloc[0]["status"] == "drafted" and before.iloc[0]["strategy"] == "request_backbill"


def test_rule_text_exists_for_every_type():
    ev = {"billing_gap": {"gap_days": 60, "missing_invoices": 1, "trailing": False},
          "silent_discount": {"avg_shortfall_pct": 0.1}, "write_off": {}, "unrecovered_failure": {}}
    for kind, e in ev.items():
        row = {"type": kind, "impact_usd": 100.0, "n_invoices": 1, "evidence": e}
        assert rule_based(row, "Acme").explanation


# ---------- scoring ----------

def test_score_counts_precision_and_recall():
    findings = pd.DataFrame([
        dict(type="billing_gap", customer_id="a", impact_usd=100.0),
        dict(type="billing_gap", customer_id="z", impact_usd=50.0),
    ])
    truth = pd.DataFrame([
        dict(type="billing_gap", customer_id="a", injected_usd=100.0),
        dict(type="billing_gap", customer_id="b", injected_usd=80.0),
    ])
    s = score(findings, truth).set_index("type").loc["billing_gap"]
    assert s["precision"] == 0.5 and s["recall"] == 0.5 and s["correct"] == 1


# ---------- integration on the shipped synthetic data ----------

needs_data = pytest.mark.skipif(not (ROOT / "data" / "injected" / "ground_truth.csv").exists(),
                                reason="run scripts/make_data.py first")


def _detect(directory):
    from leakage.detect import detect_all
    t = load_tables(ROOT / "data" / directory)
    ie = attach_expected(t["invoices"], mrr_steps(t["customers"], t["subscription_events"]))
    return detect_all(ie, t["subscription_events"], ie["invoice_date"].max())


@needs_data
def test_clean_data_has_no_planted_type_findings():
    found = _detect("clean")
    assert set(found["type"]) <= {"write_off", "unrecovered_failure"}


@needs_data
def test_injected_leakage_is_found():
    """Without noise, the improved detectors keep full precision. Unbilled expansion recall is lower than
    the first version on purpose: a single short invoice inside the grace window is ignored until the
    next cycle. The first version is checked too, so the trade-off stays visible."""
    from leakage.config import LEGACY
    from leakage.detect import detect_all
    t = load_tables(ROOT / "data" / "injected")
    truth = pd.read_csv(ROOT / "data" / "injected" / "ground_truth.csv")
    for cfg, min_unbilled_recall in ((LEGACY, 0.99), (DEFAULT, 0.80)):
        ie = attach_expected(t["invoices"], mrr_steps(t["customers"], t["subscription_events"], cfg))
        found = detect_all(ie, t["subscription_events"], ie["invoice_date"].max(), cfg)
        s = score(found, truth).set_index("type")
        assert (s["precision"] >= 0.99).all()
        assert s.loc["unbilled_expansion", "recall"] >= min_unbilled_recall
        assert s.loc[["silent_discount", "billing_gap"], "recall"].min() >= 0.99
