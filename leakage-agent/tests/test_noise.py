from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from leakage.config import DEFAULT, LEGACY
from leakage.detect import detect_billing_gaps, detect_underbilling
from leakage.evaluate import evaluate
from leakage.expected import attach_expected, load_tables, mrr_steps
from leakage.noise import NoiseRates, add_noise, add_rounding, build_noisy

ROOT = Path(__file__).resolve().parent.parent


def D(s):
    return pd.Timestamp(s)


def customers(*rows):
    df = pd.DataFrame(rows, columns=["customer_id", "customer_start_at", "initial_mrr"])
    df["customer_start_at"] = pd.to_datetime(df["customer_start_at"])
    return df


def events(*rows):
    df = pd.DataFrame(rows, columns=["customer_id", "event_timestamp", "event_type", "mrr_before", "mrr_after"])
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
    return df


def invoices(*rows):
    df = pd.DataFrame(rows, columns=["invoice_id", "customer_id", "invoice_date", "amount_usd", "payment_status"])
    df["invoice_date"] = pd.to_datetime(df["invoice_date"])
    return df


def expected(cust_rows, ev_rows, inv_rows, cfg=DEFAULT):
    return attach_expected(invoices(*inv_rows), mrr_steps(customers(*cust_rows), events(*ev_rows), cfg))


# ---------- the rules that tell noise from leakage ----------

def test_proration_is_not_leakage_but_the_same_amount_without_a_full_next_invoice_is():
    cust, ev = [("c1", "2024-01-01", 1000)], [("c1", "2024-02-01", "expansion", 1000, 2000)]
    ok = [("a", "c1", "2024-02-20", 1500, "paid"), ("b", "c1", "2024-03-19", 2000, "paid")]
    assert detect_underbilling(expected(cust, ev, ok)).empty
    stuck = [("a", "c1", "2024-02-20", 1500, "paid"), ("b", "c1", "2024-03-19", 1500, "paid")]
    assert len(detect_underbilling(expected(cust, ev, stuck))) == 1
    assert len(detect_underbilling(expected(cust, ev, ok, LEGACY), LEGACY)) == 1  # first version false alarm


def test_credit_memo_explains_a_shortfall_only_when_it_covers_it():
    cust = [("c1", "2024-01-01", 1000)]
    inv = [("a", "c1", "2024-01-01", 1000, "paid"), ("b", "c1", "2024-01-29", 600, "paid"),
           ("c", "c1", "2024-02-26", 1000, "paid")]
    ie = expected(cust, [], inv)
    assert len(detect_underbilling(ie)) == 1
    covered = pd.DataFrame([dict(invoice_id="b", customer_id="c1", credit_usd=400.0, reason="service_credit")])
    assert detect_underbilling(ie, credits=covered).empty
    partial = covered.assign(credit_usd=100.0)
    assert len(detect_underbilling(ie, credits=partial)) == 1


def test_approved_discount_is_suppressed_only_when_it_matches():
    cust = [("c1", "2024-01-01", 1000)]
    inv = [("a", "c1", "2024-01-01", 1000, "paid"), ("b", "c1", "2024-01-29", 900, "paid"),
           ("c", "c1", "2024-02-26", 900, "paid")]
    ie = expected(cust, [], inv)
    match = pd.DataFrame([dict(customer_id="c1", approved_pct=0.10, effective_from="2024-01-20", approver="x")])
    assert detect_underbilling(ie, approvals=match).empty
    deeper = match.assign(approved_pct=0.05)
    assert len(detect_underbilling(ie, approvals=deeper)) == 1  # billed 10 percent, only 5 approved


def test_recorded_downgrade_lowers_expected_billing():
    cust = [("c1", "2024-01-01", 1000)]
    ev = [("c1", "2024-01-20", "downgrade", 1000, 600)]
    inv = [("a", "c1", "2024-01-01", 1000, "paid"), ("b", "c1", "2024-01-29", 600, "paid"),
           ("c", "c1", "2024-02-26", 600, "paid")]
    assert detect_underbilling(expected(cust, ev, inv)).empty
    assert len(detect_underbilling(expected(cust, ev, inv, LEGACY), LEGACY)) == 1


def test_downgrade_applies_at_once_even_inside_the_expansion_grace_window():
    cust = [("c1", "2024-01-01", 1000)]
    ev = [("c1", "2024-01-25", "downgrade", 1000, 600)]
    inv = [("a", "c1", "2024-01-29", 600, "paid")]
    assert expected(cust, ev, inv)["expected_amount"].tolist() == [600]


def test_pause_explains_skipped_invoices_even_with_clock_skew():
    inv = [("a", "c1", "2024-01-10", 1000, "paid"), ("b", "c1", "2024-03-20", 1000, "paid")]
    ie = expected([("c1", "2024-01-01", 1000)], [], inv)
    pause = events(("c1", "2024-01-08", "pause", 1000, 1000), ("c1", "2024-03-18", "resume", 1000, 1000))
    assert detect_billing_gaps(ie, pause, D("2024-03-25")).empty  # pause is 2 days before the late invoice
    assert len(detect_billing_gaps(ie, events(), D("2024-03-25"))) == 1
    assert len(detect_billing_gaps(ie, pause, D("2024-03-25"), replace(DEFAULT, handle_pauses=False))) == 1


def test_open_ended_pause_stops_the_trailing_gap_alert():
    ie = expected([("c1", "2024-01-01", 1000)], [], [("a", "c1", "2024-01-10", 1000, "paid")])
    pause = events(("c1", "2024-01-20", "pause", 1000, 1000))
    assert detect_billing_gaps(ie, pause, D("2024-04-01")).empty
    assert len(detect_billing_gaps(ie, events(), D("2024-04-01"))) == 1


def test_late_invoices_are_tolerated_but_a_missed_invoice_is_not():
    cust = [("c1", "2024-01-01", 1000)]
    late = [("a", "c1", "2024-01-01", 1000, "paid"), ("b", "c1", "2024-02-13", 1000, "paid")]  # 43 days
    missed = [("a", "c1", "2024-01-01", 1000, "paid"), ("b", "c1", "2024-02-26", 1000, "paid")]  # 56 days
    assert detect_billing_gaps(expected(cust, [], late), events(), D("2024-02-20")).empty
    assert len(detect_billing_gaps(expected(cust, [], missed), events(), D("2024-03-01"))) == 1
    assert len(detect_billing_gaps(expected(cust, [], late, LEGACY), events(), D("2024-02-20"), LEGACY)) == 1


def test_expansion_grace_delays_but_does_not_hide_persistent_underbilling():
    cust, ev = [("c1", "2024-01-01", 1000)], [("c1", "2024-02-01", "expansion", 1000, 1600)]
    one = [("a", "c1", "2024-02-05", 1000, "paid")]                      # 4 days after: inside the grace window
    two = one + [("b", "c1", "2024-03-04", 1000, "paid")]                # next cycle: outside it
    assert detect_underbilling(expected(cust, ev, one)).empty
    found = detect_underbilling(expected(cust, ev, two))
    assert len(found) == 1 and found.iloc[0]["n_invoices"] == 1 and found.iloc[0]["impact_usd"] == 600


def test_rounding_noise_does_not_change_the_classification():
    cust, ev = [("c1", "2024-01-01", 1000)], [("c1", "2024-02-01", "expansion", 1000, 1600)]
    inv = [("a", "c1", "2024-02-20", 1001, "paid"), ("b", "c1", "2024-03-19", 999, "paid")]
    f = detect_underbilling(expected(cust, ev, inv))
    assert f["type"].tolist() == ["unbilled_expansion"]
    f_old = detect_underbilling(expected(cust, ev, inv, LEGACY), LEGACY)
    assert f_old["type"].tolist() == ["silent_discount"]  # first version confused the two


# ---------- the noise generator ----------

@pytest.fixture(scope="module")
def clean():
    path = ROOT / "data" / "clean"
    if not path.exists():
        pytest.skip("run scripts/make_data.py first")
    return load_tables(path)


def test_noise_is_reproducible_and_seed_dependent(clean):
    a1, n1 = add_noise(clean, 3)
    a2, n2 = add_noise(clean, 3)
    b, n3 = add_noise(clean, 4)
    pd.testing.assert_frame_equal(n1, n2)
    assert not n1.equals(n3)


def test_noise_cases_are_recorded_and_all_kinds_appear(clean):
    _, noise = add_noise(clean, 3)
    assert set(noise["kind"]) == {"proration", "approved_discount", "credit_memo", "pause", "downgrade",
                                  "duplicate_invoice"}
    assert noise["customer_id"].is_unique  # at most one discrete noise case per customer


def test_late_invoices_only_move_later_and_never_reorder(clean):
    noisy, _ = add_noise(clean, 3, NoiseRates(late_share=0.5))
    inv = noisy["invoices"].sort_values(["customer_id", "invoice_date"])
    assert inv.groupby("customer_id")["invoice_date"].apply(lambda s: s.is_monotonic_increasing).all()
    base = clean["invoices"].set_index("invoice_id")["invoice_date"]
    kept = noisy["invoices"].set_index("invoice_id")["invoice_date"]
    shift = (kept - base.reindex(kept.index)).dropna().dt.days
    assert shift.min() >= 0 and shift.max() <= 9 and (shift > 0).mean() > 0.3


def test_rounding_stays_within_a_fifth_of_a_percent(clean):
    rounded = add_rounding(clean, 1)["invoices"].set_index("invoice_id")["amount_usd"]
    base = clean["invoices"].set_index("invoice_id")["amount_usd"]
    moved = (rounded - base).abs()
    # up to 0.2 percent, plus at most half a dollar from rounding to whole dollars
    assert (moved <= 0.002 * base + 0.5).all() and (moved > 0).mean() > 0.15


def test_leakage_is_never_planted_on_a_noise_customer(clean):
    _, truth, noise = build_noisy(clean, 11, 7)
    assert set(truth["customer_id"]).isdisjoint(set(noise["customer_id"]))
    assert truth["type"].nunique() == 3


# ---------- end to end on the shipped noisy datasets ----------

needs_noisy = pytest.mark.skipif(not (ROOT / "data" / "noisy_b" / "ground_truth.csv").exists(),
                                 reason="run scripts/make_noisy.py first")


@needs_noisy
@pytest.mark.parametrize("name", ["noisy_a", "noisy_b"])
def test_first_version_drowns_in_noise_and_improved_version_does_not(name):
    old, old_fp, _ = evaluate(ROOT / "data" / name, LEGACY)
    new, new_fp, _ = evaluate(ROOT / "data" / name, DEFAULT)
    old, new = old.set_index("type"), new.set_index("type")
    assert old.loc["billing_gap", "precision"] < 0.2 and len(old_fp) > 500
    assert (new["precision"] >= 0.95).all() and len(new_fp) <= 5
    assert new.loc[["silent_discount", "billing_gap"], "recall"].min() >= 0.95
    assert new.loc["unbilled_expansion", "recall"] >= 0.8


@needs_noisy
def test_missing_context_records_cost_precision_and_the_confidence_floor_catches_some():
    def drop_records(t):
        t = dict(t)
        t["discount_approvals"] = t["discount_approvals"].iloc[0:0]
        t["credit_memos"] = t["credit_memos"].iloc[0:0]
        return t
    s, fp, _ = evaluate(ROOT / "data" / "noisy_b", DEFAULT, transform=drop_records)
    assert s.set_index("type").loc["silent_discount", "precision"] < 0.6
    credit = fp[fp["cause"] == "credit_memo"]
    assert len(credit) > 0 and (credit["status"] == "needs_review").all()  # single invoice, low confidence
