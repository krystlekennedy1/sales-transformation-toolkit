import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from diag.config import DEFAULT
from diag.generate import generate
from diag.rank import ACTIONS, AREA, rank
from diag.report import report
from diag.run import diagnose
from diag.score import score

EM_DASH = chr(0x2014)
SEEDS = [42, 7, 99, 2026]


@pytest.fixture(scope="module")
def planted():
    return {s: generate(s) for s in SEEDS}


@pytest.fixture(scope="module")
def results(planted):
    return {s: (diagnose(t), score(diagnose(t), t["planted"])) for s, t in planted.items()}


def test_generation_is_reproducible():
    pd.testing.assert_frame_equal(generate(42)["opps"], generate(42)["opps"])


def test_control_has_no_planted_truth():
    assert generate(42, planted=False)["planted"].empty


def test_data_shape(planted):
    t = planted[42]
    assert len(t["leads"]) == 7000 and len(t["reps"]) == 150
    assert t["opps"]["status"].isin(["open", "won", "lost"]).all()
    won = t["opps"][t["opps"].status == "won"]
    assert won["won_date"].notna().all()
    assert (t["opps"][t["opps"].status != "won"]["invoice_date"].isna()).all()


def test_most_planted_issues_are_found(results):
    recalls = [r["recall"] for _, r in results.values()]
    assert min(recalls) >= 0.7
    assert sum(recalls) / len(recalls) >= 0.8


def test_false_alarms_are_few(results):
    assert max(r["false_alarms"] for _, r in results.values()) <= 3
    assert sum(r["false_alarms"] for _, r in results.values()) / len(results) <= 2


def test_controls_are_quieter_than_planted(planted):
    for s in SEEDS:
        ctl = generate(s, planted=False)
        n_ctl = len(diagnose(ctl).query("check != 'ramp_gap'"))
        n_pl = len(diagnose(planted[s]).query("check != 'ramp_gap'"))
        assert n_ctl <= 3 and n_ctl < n_pl


def test_ranking_is_sorted_and_complete(results):
    r = results[42][0]
    assert r["priority_usd"].is_monotonic_decreasing
    assert list(r["rank"]) == list(range(1, len(r) + 1))
    assert r["check"].isin(ACTIONS).all() and r["check"].isin(AREA).all()
    assert r["confidence"].between(0.4, 0.95).all()


def test_dollar_assumptions_scale_impacts(planted):
    t = planted[42]
    lo = diagnose(t, replace(DEFAULT, win_rate=0.10))
    hi = diagnose(t, replace(DEFAULT, win_rate=0.40))
    a = lo[lo.check == "lead_response"].impact_usd.iloc[0]
    b = hi[hi.check == "lead_response"].impact_usd.iloc[0]
    assert b == pytest.approx(a * 4, rel=1e-6)


def test_small_samples_are_not_judged(planted):
    """M03 has too few open Mid-Market deals, so the coach stays silent instead of guessing."""
    f = diagnose(planted[42])
    o = planted[42]["opps"]
    n = len(o[(o.manager_id == "M03") & (o.segment == "Mid-Market") & (o.status == "open")])
    assert n < 8
    assert not ((f.check == "stale_pipeline") & (f.entity == "M03|Mid-Market")).any()


def test_report_is_readable_and_flags_assumptions(results):
    text = report(results[42][0], DEFAULT)
    assert EM_DASH not in text
    assert "Fix first" in text and "Assumptions behind the dollar figures" in text
    assert "synthetic" in text.lower()


def test_empty_report():
    assert "No findings" in report(rank(pd.DataFrame(columns=["check"])), DEFAULT)
