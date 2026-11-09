"""Turn an assessment into a 30 day coaching plan and manager briefs. Drafts only, a human reviews them."""
from __future__ import annotations

import pandas as pd

DRAFT_ONLY = True

PLAYBOOK = {
    "low_activity": dict(
        headline="Not enough selling activity",
        why="Meetings held are well below the ramp plan, and pipeline and bookings will follow it down.",
        actions=[
            "Block two 90 minute prospecting sessions every day and protect them on the calendar.",
            "Manager provides a ranked list of 40 target accounts this week so the seller is not choosing from scratch.",
            "Shadow one tenured peer for two outbound sessions, then reverse the roles.",
        ],
        talk="I want to understand what is getting in the way of your meetings. Let's look at your calendar together and find the hours.",
        metric="meetings held per week",
    ),
    "weak_pipeline": dict(
        headline="Meetings are not turning into pipeline",
        why="Activity is on plan but too few meetings become opportunities.",
        actions=[
            "Review two recorded discovery calls together and mark where qualification or next steps went missing.",
            "Agree on a standard close to every meeting: a dated next step and a named decision maker.",
            "Role play the first five minutes of discovery twice this week with the manager.",
        ],
        talk="Your activity is solid. Let's focus on what happens in the meeting that decides whether it becomes an opportunity.",
        metric="pipeline created per week",
    ),
    "single_threaded": dict(
        headline="Deals rely on one contact",
        why="Few opportunities have a second stakeholder, which tends to slow deals and lower win rate.",
        actions=[
            "For every open opportunity, add a second contact and a stated reason for involving them.",
            "Use a simple stakeholder map on each deal over a set size, reviewed in the weekly one to one.",
            "Ask for an introduction to a second contact in every meeting where a champion is identified.",
        ],
        talk="Let's pick your three biggest deals and map who else needs to say yes.",
        metric="share of opportunities with two or more contacts",
    ),
    "poor_conversion": dict(
        headline="Pipeline is there but deals are not closing",
        why="Activity and pipeline are on plan, yet bookings are well behind what that pipeline should produce.",
        actions=[
            "Run a deal review on the five oldest open opportunities and name the blocker on each.",
            "Review the last three lost deals for a common stage where they stalled.",
            "Pair the seller with a tenured peer on one live negotiation or proposal.",
        ],
        talk="You are creating good pipeline. Let's look at where deals slow down and what would move them.",
        metric="bookings versus plan",
    ),
}


def _fmt(x, money=False):
    return "n/a" if x is None or pd.isna(x) else (f"${x:,.0f}" if money else f"{x:,.1f}")


def rep_plan(row: pd.Series, rep: pd.Series, bench: dict) -> str:
    pb = PLAYBOOK[row["diagnosis"]]
    b = bench.get(rep["segment"], {})
    lines = [
        f"# 30 day ramp plan: {rep['rep_name']}", "",
        "Draft for manager review. Synthetic Meridian data. Nothing here is sent automatically.", "",
        f"**Segment:** {rep['segment']}  |  **Manager:** {rep['manager_id']}  |  **Ramp week:** {row['ramp_week']}", "",
        f"## Main gap: {pb['headline']}", "", pb["why"], "",
        "## Where they are", "",
        "| Measure | Now | Plan | Tenured peer median |", "|---|---:|---:|---:|",
        f"| Meetings per week | {_fmt(row['meetings_per_week'])} | {_fmt(row['target_meetings_per_week'])} | {_fmt(b.get('meetings'))} |",
        f"| Pipeline created per week | {_fmt(row['pipeline_per_week'], True)} | {_fmt(row['target_pipeline_per_week'], True)} | {_fmt(b.get('pipeline'), True)} |",
        f"| Opportunities with 2+ contacts | {row['multithread_pct']:.0%} | 60% | {b.get('multithread', 0):.0%} |",
        f"| Bookings versus plan | {'n/a' if row['bookings_ratio'] is None or pd.isna(row['bookings_ratio']) else format(row['bookings_ratio'], '.0%')} | 100% | n/a |",
        "", f"Estimated bookings at risk over the next 90 days: **{_fmt(row['at_risk_usd_90d'], True)}** (an estimate from the ramp plan, not a forecast).", "",
        "## Three actions for the next 30 days", "",
    ]
    lines += [f"{i}. {a}" for i, a in enumerate(pb["actions"], 1)]
    lines += ["", "## Manager opener", "", f"> {pb['talk']}", "",
              "## How to know it is working", "",
              f"Track **{pb['metric']}** weekly. Expect movement toward plan within two weeks. "
              "If there is no improvement by day 30, bring in the enablement lead to review the plan.", ""]
    return "\n".join(lines)


def manager_brief(mgr: str, rows: pd.DataFrame, reps: pd.DataFrame) -> str:
    m = rows.merge(reps[["rep_id", "rep_name"]], on="rep_id")
    risk, watch = m[m["status"] == "at_risk"], m[m["status"] == "watch"]
    lines = [f"# Ramp brief: manager {mgr}", "", "Draft for review. Synthetic Meridian data.", "",
             f"New sellers: {len(m)}  |  At risk: {len(risk)}  |  Watch: {len(watch)}  |  "
             f"On track: {(m['status'] == 'on_track').sum()}", ""]
    if len(risk):
        lines += ["## Needs coaching now", "", "| Seller | Ramp week | Gap | Bookings at risk (90 days) |", "|---|---:|---|---:|"]
        for r in risk.sort_values("at_risk_usd_90d", ascending=False).itertuples():
            lines.append(f"| {r.rep_name} | {r.ramp_week} | {PLAYBOOK[r.diagnosis]['headline']} | {_fmt(r.at_risk_usd_90d, True)} |")
        lines.append("")
    if len(watch):
        lines += ["## Keep an eye on", "", ", ".join(watch["rep_name"]), ""]
    if not len(risk) and not len(watch):
        lines += ["No sellers need attention this week.", ""]
    return "\n".join(lines)


def leader_summary(a: pd.DataFrame, reps: pd.DataFrame) -> str:
    n = len(a)
    risk = a[a["status"] == "at_risk"]
    m = a.merge(reps[["rep_id", "manager_id"]], on="rep_id")
    mgr = m[m["status"] == "at_risk"].groupby("manager_id").agg(n=("rep_id", "size"), usd=("at_risk_usd_90d", "sum"))
    lines = ["# Meridian ramp summary", "", "Draft for leadership review. Synthetic data.", "",
             f"New sellers assessed: {n}", "",
             "| Status | Sellers |", "|---|---:|"]
    for s in ["on_track", "watch", "at_risk", "too_early"]:
        lines.append(f"| {s} | {(a['status'] == s).sum()} |")
    lines += ["", f"Estimated bookings at risk over the next 90 days: **{_fmt(risk['at_risk_usd_90d'].sum(), True)}**", "",
              "## Why sellers are behind", "", "| Gap | Sellers | Bookings at risk |", "|---|---:|---:|"]
    for d, g in risk.groupby("diagnosis"):
        lines.append(f"| {PLAYBOOK[d]['headline']} | {len(g)} | {_fmt(g['at_risk_usd_90d'].sum(), True)} |")
    if len(mgr):
        lines += ["", "## Managers with the most at-risk sellers", "", "| Manager | At-risk sellers | Bookings at risk |", "|---|---:|---:|"]
        for k, r in mgr.sort_values("usd", ascending=False).head(5).iterrows():
            lines.append(f"| {k} | {int(r['n'])} | {_fmt(r['usd'], True)} |")
    lines += ["", "## What to do first", "",
              "1. Start with the largest gap type above, because one shared fix (a calendar block, a discovery review, a stakeholder map) covers several sellers.",
              "2. Give the top managers a coaching hour with enablement this week.", ""]
    return "\n".join(lines)
