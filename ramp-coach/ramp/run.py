"""Run the ramp coach: python -m ramp.run --data data/meridian --out output"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

from .assess import assess_all, peer_benchmarks
from .plan import DRAFT_ONLY, leader_summary, manager_brief, rep_plan


def run(data: str, out: str) -> pd.DataFrame:
    assert DRAFT_ONLY
    d, o = Path(data), Path(out)
    if o.exists():
        shutil.rmtree(o)
    (o / "rep_plans").mkdir(parents=True)
    (o / "manager_briefs").mkdir()
    reps = pd.read_csv(d / "reps.csv")
    weekly = pd.read_csv(d / "weekly.csv")
    a = assess_all(reps, weekly)
    bench = peer_benchmarks(reps, weekly)
    by_id = reps.set_index("rep_id")
    for _, r in a[a["status"] == "at_risk"].iterrows():
        (o / "rep_plans" / f"{r['rep_id']}.md").write_text(rep_plan(r, by_id.loc[r["rep_id"]], bench))
    m = a.merge(reps[["rep_id", "manager_id"]], on="rep_id")
    for mgr, g in m.groupby("manager_id"):
        (o / "manager_briefs" / f"{mgr}.md").write_text(manager_brief(mgr, g, reps))
    (o / "leader_summary.md").write_text(leader_summary(a, reps))
    a.to_csv(o / "assessments.csv", index=False)
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/meridian")
    ap.add_argument("--out", default="output")
    a = ap.parse_args()
    res = run(a.data, a.out)
    print(res["status"].value_counts().to_string())


if __name__ == "__main__":
    main()
