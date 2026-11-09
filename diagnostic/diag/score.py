"""Score findings against planted issues and count false alarms."""
from __future__ import annotations

import pandas as pd


def score(ranked: pd.DataFrame, planted: pd.DataFrame, top_n: int = 10) -> dict:
    scored = ranked[ranked["check"] != "ramp_gap"]    # the ramp module has its own ground truth and score
    found = set(zip(scored["check"], scored["entity"]))
    truth = set(zip(planted["check"], planted["entity"]))
    hit = found & truth
    fps = found - truth
    top = ranked.head(top_n)
    in_top = set(zip(top["check"], top["entity"])) & truth
    return dict(planted=len(truth), found=len(hit), recall=len(hit) / len(truth) if truth else 1.0,
                findings=len(found), false_alarms=len(fps), planted_in_top=len(in_top),
                precision=len(hit) / len(found) if found else 1.0,
                missed=sorted(truth - found), false_alarm_detail=sorted(fps))
