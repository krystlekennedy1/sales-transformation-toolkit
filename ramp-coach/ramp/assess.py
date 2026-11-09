"""Compare each new seller to the ramp plan, then name the most likely gap.

Order of checks matters because problems cascade: too little activity starves pipeline, and weak
pipeline starves bookings. The coach reports the earliest broken link in that chain.
"""
from __future__ import annotations

import pandas as pd

from . import config as C
from .config import Thresholds

COLUMNS = ["rep_id", "ramp_week", "status", "diagnosis", "meetings_ratio", "pipeline_ratio",
           "bookings_ratio", "multithread_pct", "meetings_per_week", "target_meetings_per_week",
           "pipeline_per_week", "target_pipeline_per_week", "at_risk_usd_90d", "note"]


def _ratio(actual: float, expected: float):
    return None if expected <= 0 else actual / expected


def assess_rep(rep, g: pd.DataFrame, cfg: Thresholds = Thresholds()) -> dict:
    g = g.sort_values("ramp_week")
    week = int(g["ramp_week"].max())
    seg = rep.segment
    cycle = C.SEGMENTS[seg]["cycle_weeks"]
    out = dict(rep_id=rep.rep_id, ramp_week=week, status="too_early", diagnosis="none",
               meetings_ratio=None, pipeline_ratio=None, bookings_ratio=None, multithread_pct=None,
               meetings_per_week=None, target_meetings_per_week=None, pipeline_per_week=None,
               target_pipeline_per_week=None, at_risk_usd_90d=0.0, note="")
    if week < cfg.min_week:
        out["note"] = f"Ramp week {week}: too early to judge."
        return out

    win = g.tail(cfg.window)
    weeks = win["ramp_week"].tolist()
    exp_m = sum(C.meetings_target(w) for w in weeks)
    exp_p = sum(C.pipeline_target(seg, w) for w in weeks)
    m_ratio = _ratio(win["meetings"].sum(), exp_m)
    p_ratio = _ratio(win["pipeline_created"].sum(), exp_p)
    mt = float(g.tail(6)["multithread_pct"].mean())

    book_ratio = None
    if week >= cycle + cfg.book_wait:
        exp_b = sum(C.bookings_target(seg, w) for w in g["ramp_week"])
        book_ratio = _ratio(g["closed_won"].sum(), exp_b)

    out.update(meetings_ratio=m_ratio, pipeline_ratio=p_ratio, bookings_ratio=book_ratio,
               multithread_pct=mt, meetings_per_week=win["meetings"].mean(),
               target_meetings_per_week=exp_m / len(weeks), pipeline_per_week=win["pipeline_created"].mean(),
               target_pipeline_per_week=exp_p / len(weeks))

    diagnosis, binding = "none", None
    if m_ratio < cfg.at_risk:
        diagnosis, binding = "low_activity", m_ratio
    elif p_ratio < cfg.at_risk:
        diagnosis, binding = "weak_pipeline", p_ratio
    elif mt < cfg.mt_low:
        diagnosis, binding = "single_threaded", book_ratio if book_ratio is not None else max(mt / C.MULTITHREAD_HEALTHY, 0.3)
    elif book_ratio is not None and book_ratio < cfg.book_low:
        diagnosis, binding = "poor_conversion", book_ratio

    if diagnosis != "none":
        out["status"], out["diagnosis"] = "at_risk", diagnosis
        future = sum(C.bookings_target(seg, w) for w in range(week + 1, week + 14))
        out["at_risk_usd_90d"] = round(future * (1 - min(binding, 1.0)), 2)
    else:
        watch_vals = [v for v in (m_ratio, p_ratio, book_ratio) if v is not None]
        out["status"] = "watch" if min(watch_vals) < cfg.watch else "on_track"
        if book_ratio is None:
            out["note"] = "Conversion cannot be judged until bookings from this ramp have had time to close."
    return out


def assess_all(reps: pd.DataFrame, weekly: pd.DataFrame, cfg: Thresholds = Thresholds()) -> pd.DataFrame:
    rows = []
    for rep in reps[reps["tenure"] == "new"].itertuples():
        g = weekly[weekly["rep_id"] == rep.rep_id]
        if not g.empty:
            rows.append(assess_rep(rep, g, cfg))
    return pd.DataFrame(rows, columns=COLUMNS)


def peer_benchmarks(reps: pd.DataFrame, weekly: pd.DataFrame) -> dict:
    """Median weekly activity of tenured sellers, by segment."""
    t = weekly.merge(reps[["rep_id", "segment", "tenure"]], on="rep_id")
    t = t[t["tenure"] == "tenured"]
    g = t.groupby("segment").agg(meetings=("meetings", "median"), pipeline=("pipeline_created", "median"),
                                 multithread=("multithread_pct", "median"))
    return g.to_dict("index")
