import re
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ramp import config as C
from ramp.assess import assess_all, assess_rep, peer_benchmarks
from ramp.generate import generate
from ramp.plan import PLAYBOOK, leader_summary, manager_brief, rep_plan
from ramp.run import run
from ramp.score import score

EM_DASH = chr(0x2014)


@pytest.fixture(scope="module")
def data():
    reps, weekly, truth = generate(42)
    return reps, weekly, truth, assess_all(reps, weekly)


def test_generation_is_reproducible():
    a = generate(42)[1]
    b = generate(42)[1]
    pd.testing.assert_frame_equal(a, b)


def test_company_shape(data):
    reps, weekly, truth, _ = data
    assert len(reps) == 150
    assert (reps["tenure"] == "new").sum() == 40
    assert (weekly[["meetings", "pipeline_created", "closed_won"]] >= 0).all().all()
    assert weekly["multithread_pct"].between(0, 1).all()


def test_ramp_plan_is_monotonic_and_capped():
    vals = [C.ramp_pct(w) for w in range(1, 30)]
    assert vals == sorted(vals) and max(vals) == 1.0
    assert C.bookings_target("SMB", 3) == 0.0          # nothing can close before one sales cycle
    assert C.bookings_target("SMB", 20) > 0


def test_too_early_sellers_are_not_judged(data):
    reps, weekly, _, _ = data
    rep = next(reps[reps.tenure == "new"].itertuples())
    short = weekly[weekly.rep_id == rep.rep_id].head(2)
    assert assess_rep(rep, short)["status"] == "too_early"


def test_planted_problems_are_found_without_false_alarms(data):
    reps, weekly, truth, a = data
    s = score(a, truth, reps)
    assert s["precision"] >= 0.9
    assert s["detectable_recall"] >= 0.95
    assert s["diagnosis_accuracy"] >= 0.9


@pytest.mark.parametrize("seed", [7, 99, 2026])
def test_holdout_seeds(seed):
    reps, weekly, truth = generate(seed)
    s = score(assess_all(reps, weekly), truth, reps)
    assert s["precision"] >= 0.85
    assert s["detectable_recall"] >= 0.9


def test_conversion_problems_need_time_to_show(data):
    """A young poor_conversion seller cannot be caught yet, and the coach should say so, not guess."""
    reps, weekly, truth, a = data
    young = truth[(truth.archetype == "poor_conversion")]
    for r in young.itertuples():
        seg = reps.set_index("rep_id").loc[r.rep_id, "segment"]
        if r.ramp_weeks < C.SEGMENTS[seg]["cycle_weeks"] + 4:
            row = a[a.rep_id == r.rep_id].iloc[0]
            assert row["bookings_ratio"] is None or pd.isna(row["bookings_ratio"])


def test_at_risk_dollars_are_positive_and_bounded(data):
    _, _, _, a = data
    risk = a[a.status == "at_risk"]
    assert (risk.at_risk_usd_90d > 0).all()
    assert (a[a.status != "at_risk"].at_risk_usd_90d == 0).all()


def test_outputs_are_drafts_without_em_dashes(tmp_path):
    reps, weekly, truth = generate(42)
    d = tmp_path / "d"
    d.mkdir()
    reps.to_csv(d / "reps.csv", index=False)
    weekly.to_csv(d / "weekly.csv", index=False)
    a = run(str(d), str(tmp_path / "out"))
    plans = list((tmp_path / "out" / "rep_plans").glob("*.md"))
    assert len(plans) == (a.status == "at_risk").sum()
    for f in list((tmp_path / "out").rglob("*.md")):
        text = f.read_text()
        assert EM_DASH not in text
        if "rep_plans" in str(f):
            assert "Draft for manager review" in text
    assert (tmp_path / "out" / "leader_summary.md").exists()


def test_every_diagnosis_has_a_playbook(data):
    _, _, _, a = data
    for d in a.diagnosis.unique():
        assert d == "none" or d in PLAYBOOK
    for pb in PLAYBOOK.values():
        assert len(pb["actions"]) == 3 and EM_DASH not in str(pb)


def test_peer_benchmarks_near_plan(data):
    reps, weekly, _, _ = data
    b = peer_benchmarks(reps, weekly)
    assert 6.5 <= b["SMB"]["meetings"] <= 9.5


def test_leader_summary_totals_match(data):
    reps, _, _, a = data
    text = leader_summary(a, reps)
    total = a[a.status == "at_risk"].at_risk_usd_90d.sum()
    assert f"${total:,.0f}" in text
    assert re.search(r"New sellers assessed: 40", text)
