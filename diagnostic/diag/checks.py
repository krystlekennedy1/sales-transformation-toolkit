"""Ten evidence-based checks. Each looks at records, compares an entity (a manager, a segment or a lead
source) with the typical entity, and reports a finding only when it stands well apart.

A finding has: the evidence, an estimated dollar impact with its basis, and a sample size that drives
confidence. "Typical" is the median across entities, so a few bad entities do not hide themselves.
"""
from __future__ import annotations

import pandas as pd

from .config import DEFAULT, Assumptions

COLUMNS = ["check", "entity", "value", "baseline", "n", "n_ref", "impact_usd", "basis", "evidence"]


def _row(check, entity, value, baseline, n, n_ref, impact, basis, evidence):
    return dict(check=check, entity=entity, value=float(value), baseline=float(baseline), n=int(n),
                n_ref=int(n_ref), impact_usd=float(impact), basis=basis, evidence=evidence)


def _end(t):
    return pd.Timestamp(t["as_of"])


def _won(t):
    return t["opps"][t["opps"]["status"] == "won"].copy()


def stale_pipeline(t, a: Assumptions = DEFAULT):
    o = t["opps"][t["opps"]["status"] == "open"].copy()
    o["stale"] = (_end(t) - o["last_activity"]).dt.days > a.stale_days
    g = o.groupby(["manager_id", "segment"])
    s = g.agg(n=("opp_id", "size"), share=("stale", "mean")).query("n >= 8")
    base = s["share"].median()
    rows = []
    for (m, seg), r in s.iterrows():
        if r["share"] >= max(0.20, a.ratio * base):
            x = o[(o.manager_id == m) & (o.segment == seg) & o.stale]
            rows.append(_row("stale_pipeline", f"{m}|{seg}", r["share"], base, r["n"], 30,
                             x["amount"].sum() * a.win_rate, "stale open pipeline x win rate",
                             f"{r['share']:.0%} of {int(r['n'])} open deals untouched {a.stale_days}+ days "
                             f"(typical {base:.0%}); ${x['amount'].sum():,.0f} of pipeline"))
    return rows


def past_due_close_dates(t, a: Assumptions = DEFAULT):
    o = t["opps"][t["opps"]["status"] == "open"].copy()
    o["late"] = o["close_date_current"] < _end(t)
    s = o.groupby("manager_id").agg(n=("opp_id", "size"), share=("late", "mean")).query("n >= 10")
    base = s["share"].median()
    rows = []
    for m, r in s.iterrows():
        if r["share"] >= max(0.15, a.ratio * base):
            x = o[(o.manager_id == m) & o.late]
            rows.append(_row("past_due_close_dates", m, r["share"], base, r["n"], 30,
                             x["amount"].sum() * a.win_rate, "past-due open pipeline x win rate",
                             f"{r['share']:.0%} of open deals have a close date in the past (typical {base:.0%})"))
    return rows


def close_date_slippage(t, a: Assumptions = DEFAULT):
    o = t["opps"][t["opps"]["status"] == "open"].copy()
    s = o.groupby("manager_id").agg(n=("opp_id", "size"), pushes=("pushes", "mean")).query("n >= 10")
    base = s["pushes"].median()
    rows = []
    for m, r in s.iterrows():
        if r["pushes"] >= max(1.0, a.ratio * base):
            x = o[(o.manager_id == m) & (o.pushes >= 2)]
            rows.append(_row("close_date_slippage", m, r["pushes"], base, r["n"], 30,
                             x["amount"].sum() * a.win_rate, "pipeline pushed 2+ times x win rate",
                             f"open deals have been pushed {r['pushes']:.1f} times on average (typical {base:.1f})"))
    return rows


def forecast_bias(t, a: Assumptions = DEFAULT):
    f = t["forecast"].copy()
    f = f[f["actual_usd"] > 0]
    f["ratio"] = f["forecast_usd"] / f["actual_usd"]
    rows = []
    for m, g in f.groupby("manager_id"):
        if len(g) < 5:
            continue
        med = g["ratio"].median()
        over, under = (g["ratio"] > 1.1).sum(), (g["ratio"] < 0.9).sum()
        if (med >= 1.2 and over >= len(g) - 1) or (med <= 0.8 and under >= len(g) - 1):
            err = (g["forecast_usd"] - g["actual_usd"]).abs().sum()
            way = "above" if med > 1 else "below"
            rows.append(_row("forecast_bias", m, med, 1.0, len(g), 6, err, "total forecast error in dollars",
                             f"forecast ran {abs(med - 1):.0%} {way} actual bookings in {max(over, under)} of {len(g)} months"))
    return rows


def lead_response(t, a: Assumptions = DEFAULT):
    L, O = t["leads"].copy(), t["opps"]
    L["slow"] = L["first_response_hours"] > 24
    s = L.groupby("source").agg(n=("lead_id", "size"), share=("slow", "mean"))
    base = s["share"].median()
    rows = []
    for src, r in s.iterrows():
        if r["n"] >= 100 and r["share"] >= max(0.15, a.ratio * base):
            g = L[L.source == src]
            fast, slow = g[~g.slow], g[g.slow]
            gap = max(0.0, fast["converted"].mean() - slow["converted"].mean()) if len(slow) and len(fast) else 0.0
            avg = O["amount"].mean()
            rows.append(_row("lead_response", src, r["share"], base, r["n"], 300,
                             len(slow) * gap * avg * a.win_rate, "slow leads x conversion gap x avg deal x win rate",
                             f"{r['share']:.0%} of {src} leads wait over 24 hours (typical {base:.0%}); "
                             f"converted {slow['converted'].mean():.0%} vs {fast['converted'].mean():.0%} when fast"))
    return rows


def discount_governance(t, a: Assumptions = DEFAULT):
    o = t["opps"].copy()
    o["bad"] = (o["discount_pct"] > a.discount_limit) & (~o["discount_approved"])
    s = o.groupby("source").agg(n=("opp_id", "size"), share=("bad", "mean"), k=("bad", "sum"))
    base = s["share"].median()
    rows = []
    for src, r in s.iterrows():
        if r["k"] >= 10 and r["share"] >= max(0.08, a.ratio * base):
            x = o[(o.source == src) & o.bad]
            rows.append(_row("discount_governance", src, r["share"], base, r["n"], 150,
                             (x["amount"] * x["discount_pct"]).sum(), "discount given without approval",
                             f"{int(r['k'])} deals over the {a.discount_limit:.0%} limit with no approval "
                             f"({r['share']:.0%} of {src} deals, typical {base:.0%})"))
    return rows


def invoice_delay(t, a: Assumptions = DEFAULT):
    w = _won(t).dropna(subset=["invoice_date"])
    w["lag"] = (w["invoice_date"] - w["won_date"]).dt.days
    s = w.groupby("manager_id").agg(n=("opp_id", "size"), med=("lag", "median")).query("n >= 10")
    base = s["med"].median()
    rows = []
    for m, r in s.iterrows():
        if r["med"] >= max(10, a.ratio * base):
            x = w[(w.manager_id == m) & (w.lag > a.ratio * base)]
            rows.append(_row("invoice_delay", m, r["med"], base, r["n"], 30,
                             x["amount"].sum() * a.late_invoice_cost, "late-invoiced revenue x delay cost",
                             f"median {r['med']:.0f} days from win to invoice (typical {base:.0f}); "
                             f"${x['amount'].sum():,.0f} invoiced late"))
    return rows


def missing_invoice(t, a: Assumptions = DEFAULT):
    w = _won(t)
    w = w[(_end(t) - w["won_date"]).dt.days > 30]
    w["miss"] = w["invoice_date"].isna()
    rows = []
    for m, g in w.groupby("manager_id"):
        k = int(g["miss"].sum())
        if k >= 3 and g["miss"].mean() >= 0.05:
            rows.append(_row("missing_invoice", m, g["miss"].mean(), 0.0, len(g), 20,
                             g.loc[g["miss"], "amount"].sum(), "won deals never invoiced",
                             f"{k} of {len(g)} won deals older than 30 days have no invoice"))
    return rows


def handoff_completeness(t, a: Assumptions = DEFAULT):
    w = _won(t)
    w["bad"] = ~w["handoff_complete"].astype(bool)
    s = w.groupby("manager_id").agg(n=("opp_id", "size"), share=("bad", "mean"), k=("bad", "sum")).query("n >= 10")
    base = s["share"].median()
    rows = []
    for m, r in s.iterrows():
        if r["k"] >= 3 and r["share"] >= max(0.15, a.ratio * base):
            rows.append(_row("handoff_completeness", m, r["share"], base, r["n"], 30,
                             r["k"] * a.rework_hours * a.hourly_cost, "rework hours x hourly cost",
                             f"{r['share']:.0%} of {int(r['n'])} won deals handed off with missing fields (typical {base:.0%})"))
    return rows


def ramp_gap(t, a: Assumptions = DEFAULT):
    from ramp.assess import assess_all
    asm = assess_all(t["reps"], t["weekly"])
    asm = asm.merge(t["reps"][["rep_id", "manager_id"]], on="rep_id")
    risk = asm[asm["status"] == "at_risk"]
    rows = []
    for m, g in risk.groupby("manager_id"):
        if len(g) >= 2:
            rows.append(_row("ramp_gap", m, len(g), 0, len(asm[asm.manager_id == m]), 3, g["at_risk_usd_90d"].sum(),
                             "planned bookings shortfall, next 90 days",
                             f"{len(g)} new sellers behind ramp plan: " + ", ".join(sorted(g["diagnosis"].unique()))))
    return rows


CHECKS = [stale_pipeline, past_due_close_dates, close_date_slippage, forecast_bias, lead_response,
          discount_governance, invoice_delay, missing_invoice, handoff_completeness, ramp_gap]


def run_checks(t: dict, a: Assumptions = DEFAULT) -> pd.DataFrame:
    rows = []
    for c in CHECKS:
        rows += c(t, a)
    return pd.DataFrame(rows, columns=COLUMNS)
