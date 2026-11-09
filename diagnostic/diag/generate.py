"""Synthetic Meridian pipeline: leads, opportunities, forecasts, with planted organization issues.

Reuses the ramp coach's company (same sellers and managers). With planted=False the company has the
same natural noise but no planted issues, which is the control used to count false alarms.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ramp import config as RC
from ramp.generate import generate as generate_ramp

from .config import AS_OF

SOURCES = ["Web", "Partner", "Outbound", "Referral", "Event"]
SOURCE_P = [0.30, 0.15, 0.25, 0.15, 0.15]
LEAD_CONV = {"Web": 0.30, "Partner": 0.35, "Outbound": 0.20, "Referral": 0.45, "Event": 0.25}
WIN_P = {"Web": 0.24, "Partner": 0.24, "Outbound": 0.22, "Referral": 0.32, "Event": 0.22}
N_LEADS = 7000

PLANTED = pd.DataFrame([
    ("stale_pipeline", "M03|Mid-Market", "40%+ of open Mid-Market deals untouched for 30+ days"),
    ("stale_pipeline", "M09|Mid-Market", "40%+ of open Mid-Market deals untouched for 30+ days"),
    ("forecast_bias", "M05", "forecasts about 35% above what closes"),
    ("forecast_bias", "M11", "forecasts about 30% below what closes (sandbagging)"),
    ("invoice_delay", "M07", "won deals invoiced about three weeks late"),
    ("discount_governance", "Partner", "deep Partner discounts mostly unapproved"),
    ("lead_response", "Web", "nearly half of Web leads wait over a day for a first response"),
    ("handoff_completeness", "M12", "half of won deals handed off with missing fields"),
    ("close_date_slippage", "M02", "close dates pushed again and again"),
    ("missing_invoice", "M14", "about 15% of won deals never invoiced"),
], columns=["check", "entity", "description"])


def generate(seed: int = 42, planted: bool = True, as_of: str = AS_OF) -> dict:
    reps, weekly, ramp_truth = generate_ramp(seed, as_of)
    rng = np.random.default_rng(seed + 1000)
    end = pd.Timestamp(as_of)
    start = end - pd.Timedelta(days=180)
    rid = reps["rep_id"].to_numpy()
    seg = reps.set_index("rep_id")["segment"].to_dict()
    mgr = reps.set_index("rep_id")["manager_id"].to_dict()
    hire = pd.to_datetime(reps["hire_date"]).to_numpy()
    base_w = np.where(reps["tenure"] == "new", 0.6, 1.0)

    P = planted
    leads, opps = [], []
    for i in range(N_LEADS):
        src = str(rng.choice(SOURCES, p=SOURCE_P))
        created = start + pd.Timedelta(hours=float(rng.uniform(0, 180 * 24)))
        resp = float(rng.lognormal(np.log(2), 1.3))
        if P and src == "Web" and rng.random() < 0.45:
            resp = float(rng.uniform(25, 90))
        conv = LEAD_CONV[src] * (0.5 if resp > 24 else 1.0)
        converted = rng.random() < conv
        opp_id = None
        if converted:
            ok = hire <= (created - pd.Timedelta(days=14)).to_datetime64()
            w = base_w * ok
            if w.sum() == 0:
                converted = False
            else:
                rep = str(rng.choice(rid, p=w / w.sum()))
                opp_id = f"O{len(opps) + 1:05d}"
                opps.append(_opp(rng, opp_id, rep, src, created, resp, seg, mgr, end, P))
        leads.append(dict(lead_id=f"L{i + 1:05d}", source=src, created=created.normalize(),
                          first_response_hours=round(resp, 1), converted=bool(converted), opp_id=opp_id))
    opps = pd.DataFrame(opps)
    leads = pd.DataFrame(leads)

    won = opps[opps["status"] == "won"].copy()
    won["month"] = pd.to_datetime(won["won_date"]).dt.to_period("M").astype(str)
    act = won.groupby(["manager_id", "month"])["amount"].sum().reset_index(name="actual_usd")
    bias = {"M05": 1.35, "M11": 0.70} if P else {}
    act["forecast_usd"] = [round(r.actual_usd * bias.get(r.manager_id, 1.0) * rng.lognormal(0, 0.15), 2)
                           for r in act.itertuples()]
    # drop the current partial month, which cannot be compared yet
    act = act[act["month"] < end.to_period("M").strftime("%Y-%m")].reset_index(drop=True)
    return dict(reps=reps, weekly=weekly, ramp_truth=ramp_truth, leads=leads, opps=opps,
                forecast=act, planted=PLANTED if P else PLANTED.iloc[0:0])


def _opp(rng, opp_id, rep, src, lead_created, resp, seg, mgr, end, P):
    s, m = seg[rep], mgr[rep]
    cfg = RC.SEGMENTS[s]
    created = (lead_created + pd.Timedelta(hours=resp)).normalize()
    amount = round(cfg["deal_size"] * float(rng.lognormal(0, 0.35)), 2)
    close = created + pd.Timedelta(days=float(cfg["cycle_weeks"] * 7 * rng.lognormal(0, 0.25))).round("D")
    # discount and approval
    r = rng.random()
    disc = rng.uniform(0, 0.10) if r < 0.70 else rng.uniform(0.10, 0.15) if r < 0.90 else rng.uniform(0.16, 0.25)
    approved = True if disc <= 0.15 else bool(rng.random() < 0.95)
    if P and src == "Partner" and rng.random() < 0.35:
        disc, approved = float(rng.uniform(0.18, 0.30)), bool(rng.random() < 0.30)
    row = dict(opp_id=opp_id, rep_id=rep, manager_id=m, segment=s, source=src, created=created,
               amount=amount, discount_pct=round(float(disc), 3), discount_approved=approved,
               close_date_original=close, close_date_current=pd.NaT, pushes=0, last_activity=pd.NaT,
               won_date=pd.NaT, invoice_date=pd.NaT, handoff_complete=pd.NA, status="open")
    if close <= end:
        row["status"] = "won" if rng.random() < WIN_P[src] else "lost"
        if row["status"] == "won":
            row["won_date"] = close
            row["handoff_complete"] = bool(rng.random() < (0.50 if P and m == "M12" else 0.95))
            never = 0.15 if P and m == "M14" else 0.004
            if (end - close).days > 30 and rng.random() < never:
                pass
            else:
                lag = 1 + rng.poisson(22 if P and m == "M07" else 2)
                inv = close + pd.Timedelta(days=int(lag))
                row["invoice_date"] = inv if inv <= end else pd.NaT
        return row
    pushes = int(rng.poisson(2.2 if P and m == "M02" else 0.35))
    row["pushes"] = pushes
    row["close_date_current"] = close + pd.Timedelta(days=7 * pushes)
    if rng.random() < 0.06:
        row["close_date_current"] = end - pd.Timedelta(days=int(rng.integers(1, 30)))
    stale_p = 0.45 if P and m in ("M03", "M09") and s == "Mid-Market" else 0.07
    if rng.random() < stale_p:
        last = end - pd.Timedelta(days=int(rng.integers(31, 76)))
    else:
        last = end - pd.Timedelta(days=int(min(28, rng.exponential(6))))
    row["last_activity"] = max(last, created)
    return row
