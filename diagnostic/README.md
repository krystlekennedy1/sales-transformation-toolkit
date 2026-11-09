# Meridian sales organization diagnostic (prototype)

Scans a sales organization's records for process problems, ranks them by estimated dollar impact, and
names an owner and a first fix for each. It runs on a fictional company (Meridian, 150 sellers, 15
managers, 7,000 leads over six months) with synthetic data only. The new-seller ramp coach is built
in as one of the ten checks.

## Quick start

```bash
pip install -r requirements.txt
python -m diag.run --seed 42 --out output        # planted company, writes the report
python -m diag.run --seed 42 --control           # same noise, no planted issues
python -m pytest -q                              # 11 tests
python scripts/evaluate.py                       # scoring on four seeds plus a sensitivity test
```

Open `output/diagnostic_report.md` first. `output/findings.csv` has every number behind it.

## The ten checks

| Area | Check | Compares | Flags when |
|---|---|---|---|
| Pipeline | Untouched pipeline | share of open deals with no activity in 30 days, per manager and segment | 2x typical and at least 20% |
| Pipeline | Past-due close dates | share of open deals with a close date in the past | 2x typical and at least 15% |
| Pipeline | Repeated close date pushes | average pushes per open deal | 2x typical and at least 1.0 |
| Forecast | Forecast bias | forecast versus actual bookings, per month | 20% off in almost every month |
| Lead to opportunity | Slow lead response | share of leads waiting over 24 hours, per source | 2x typical and at least 15% |
| Revenue protection | Unapproved discounts | deals over the 15% limit with no approval, per source | 2x typical, at least 8% and 10 deals |
| Lead to cash | Late invoicing | median days from win to invoice | 2x typical and at least 10 days |
| Revenue protection | Won deals never invoiced | won deals over 30 days old with no invoice | 3+ deals and at least 5% |
| Lead to cash | Incomplete handoffs | won deals missing required fields | 2x typical, at least 15% and 3 deals |
| People and ramp | New sellers behind ramp | at-risk new sellers per manager (ramp coach) | 2 or more |

"Typical" is the median across managers, segments or sources, so a few bad ones do not hide
themselves. Findings are ranked by estimated impact times a confidence score that grows with sample size.

## Results

Each seed builds a new company with 10 planted issues (manager-level, source-level and segment-level).
The ramp check has its own score in the ramp coach and is left out here.

| Seed | Found | Recall | False alarms | Precision |
|---:|---:|---:|---:|---:|
| 42 | 9 of 10 | 90% | 0 | 100% |
| 7 | 8 of 10 | 80% | 0 | 100% |
| 99 | 8 of 10 | 80% | 3 | 73% |
| 2026 | 9 of 10 | 90% | 1 | 90% |

Control companies (same noise, nothing planted) produced 0, 3, 2 and 0 findings, so expect roughly
one or two false leads per scan.

**What was missed, and why**
- Won deals never invoiced (manager M14) was missed on three seeds. At about 30 won deals per manager, a
  leak needs to reach roughly 10 to 15 percent to clear the 3 deal minimum. Smaller leaks need more data.
- A forecast bias was missed on two seeds because the rule asks for a consistent miss in nearly every month.
- One untouched-pipeline case was missed because that manager had only 6 open Mid-Market deals, below
  the minimum of 8. Staying silent on a tiny sample is by design.

**Two changes I made after seeing results.** I raised the planted invoicing leak from 7 to 15 percent
because 7 percent was a single deal and not detectable by anyone. I also added a 3 deal minimum to
the handoff check after it flagged a manager over 2 incomplete handoffs. Both are disclosed so the
scores are not read as untouched.

**Do the dollar assumptions change the ranking?** On seed 42, the number of planted issues in the top 10
was the same (7) across five very different combinations of win rate, late invoice cost and hourly cost.

## Read this before trusting the numbers

- **I wrote the data and the checks.** Planted issues are clean and each has one cause. Real
  organizations have overlapping problems, messy fields and years of history. Expect worse accuracy.
- **Dollar figures are assumptions.** Win rate, delay cost and rework cost are guesses in
  `diag/config.py`. Impacts are also in different units (lost bookings, rework cost, forecast error),
  so the ranking is a starting order for discussion, not a precise one.
- **Correlation is not cause.** A finding says where to look. It does not say why. A manager with
  stale pipeline may have a territory problem, not a discipline problem.
- **Forecasts here are generated from actuals plus noise.** Real forecast error behaves differently.
- **The ramp check uses separate activity data**, not the opportunities above, so the two views are not
  linked at the deal level.
- **Synthetic data only.** Do not run this on real CRM, billing or HR data without the right approval.

## Files

`diag/generate.py` builds the company and the planted issues. `diag/checks.py` holds the ten checks,
`diag/rank.py` ranks and assigns owners, `diag/report.py` writes the report. The ramp coach is reused from the sibling `ramp-coach` folder of the toolkit repo.
