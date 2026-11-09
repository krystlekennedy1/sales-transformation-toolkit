"""Synthetic Meridian data: 150 sellers (40 new, 110 tenured), weekly activity and bookings.

Some new sellers get a planted ramp problem so the coach can be scored against ground truth.
Nothing here comes from a real company or a real CRM.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C

ARCHETYPES = ["healthy", "low_activity", "weak_pipeline", "single_threaded", "poor_conversion"]
N_NEW, N_TENURED, N_MANAGERS = 40, 110, 15
TENURED_WEEKS = 13


def _week_rows(rng, rep_id, segment, weeks, arch, rep_mult, start_dates, ramp_weeks):
    m_mult = {"low_activity": 0.55}.get(arch, 1.0) * rep_mult
    p_mult = {"low_activity": 0.55, "weak_pipeline": 0.50}.get(arch, 1.0) * rep_mult
    win_mult = {"poor_conversion": 0.45, "single_threaded": 0.60}.get(arch, 1.0)
    mt_mean = 0.20 if arch == "single_threaded" else C.MULTITHREAD_HEALTHY
    cycle = C.SEGMENTS[segment]["cycle_weeks"]
    deal = C.SEGMENTS[segment]["deal_size"]
    rows, pipes = [], {}
    for i, w in enumerate(weeks):
        meet = C.meetings_target(w) * m_mult * rng.lognormal(0, 0.15)
        pipe = C.pipeline_target(segment, w) * p_mult * rng.lognormal(0, 0.15)
        pipes[i] = pipe
        src = pipes.get(i - cycle)
        won = C.WIN_RATE * win_mult * src * rng.lognormal(0, 0.45) if src is not None else 0.0
        rows.append(dict(
            rep_id=rep_id, week_start=start_dates[i], ramp_week=ramp_weeks[i],
            meetings=int(round(meet)), pipeline_created=round(pipe, 2),
            opps_created=max(0, int(round(pipe / deal))), closed_won=round(won, 2),
            multithread_pct=float(np.clip(rng.normal(mt_mean, 0.08), 0.02, 0.98)),
        ))
    return rows


def generate(seed: int = 42, as_of: str = C.AS_OF):
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(as_of)
    n = N_NEW + N_TENURED
    segments = rng.choice(list(C.SEGMENTS), size=n, p=[0.6, 0.4])
    managers = [f"M{(i % N_MANAGERS) + 1:02d}" for i in rng.permutation(n)]
    new_flags = np.array([True] * N_NEW + [False] * N_TENURED)
    order = rng.permutation(n)
    new_flags = new_flags[order]

    archs = np.array(["healthy"] * 24 + ["low_activity"] * 4 + ["weak_pipeline"] * 4
                     + ["single_threaded"] * 4 + ["poor_conversion"] * 4)
    archs = rng.permutation(archs)

    reps, weekly, truth = [], [], []
    k = 0
    for i in range(n):
        rep_id = f"R{i + 1:03d}"
        seg = str(segments[i])
        if new_flags[i]:
            done = int(rng.integers(5, 27))                      # completed ramp weeks
            hire = end - pd.Timedelta(days=7 * done)
            arch = str(archs[k]); k += 1
            weeks = list(range(1, done + 1))
            starts = [hire + pd.Timedelta(days=7 * (w - 1)) for w in weeks]
            mult = float(rng.uniform(0.95, 1.12))
            weekly += _week_rows(rng, rep_id, seg, weeks, arch, mult, starts, weeks)
            truth.append(dict(rep_id=rep_id, archetype=arch, ramp_weeks=done))
            tenure = "new"
        else:
            hire = end - pd.Timedelta(days=int(rng.integers(400, 2500)))
            weeks = [26] * TENURED_WEEKS
            starts = [end - pd.Timedelta(days=7 * (TENURED_WEEKS - j)) for j in range(TENURED_WEEKS)]
            mult = float(rng.uniform(0.85, 1.15))
            rows = _week_rows(rng, rep_id, seg, weeks, "healthy", mult, starts, [0] * TENURED_WEEKS)
            # tenured sellers have closed pipeline from earlier weeks, so book steady-state wins
            for r in rows:
                r["closed_won"] = round(C.pipeline_target(seg, 26) * C.WIN_RATE * mult * rng.lognormal(0, 0.35), 2)
            weekly += rows
            tenure = "tenured"
        reps.append(dict(rep_id=rep_id, rep_name=f"Rep {i + 1:03d}", segment=seg, manager_id=managers[i],
                         hire_date=hire.date().isoformat(), quota_month=C.SEGMENTS[seg]["quota_month"],
                         tenure=tenure))
    return pd.DataFrame(reps), pd.DataFrame(weekly), pd.DataFrame(truth)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/meridian")
    a = ap.parse_args()
    reps, weekly, truth = generate(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    reps.to_csv(out / "reps.csv", index=False)
    weekly.to_csv(out / "weekly.csv", index=False)
    truth.to_csv(out / "ground_truth.csv", index=False)
    print(f"wrote {len(reps)} reps, {len(weekly)} rep-weeks to {out}")


if __name__ == "__main__":
    main()
