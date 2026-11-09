# New-rep ramp coach (prototype)

Compares each new seller to a ramp plan, names the most likely reason they are behind, and drafts a
30 day coaching plan for their manager. It runs on a fictional company (Meridian, 150 sellers) with
synthetic data only. It never sends anything: every output is a draft for a person to review.

## Quick start

```bash
pip install -r requirements.txt
python -m ramp.generate --seed 42 --out data/meridian   # build the synthetic company
python -m ramp.run --data data/meridian --out output     # assess, diagnose, write plans
python -m pytest -q                                      # 14 tests
python scripts/evaluate.py                               # score on four seeds
```

## What you get

| Output | For | Contents |
|---|---|---|
| `output/leader_summary.md` | Sales leader | Status counts, gap types, bookings at risk, managers who need support |
| `output/manager_briefs/<manager>.md` | First-line manager | Their new sellers, who needs coaching now, who to watch |
| `output/rep_plans/<rep>.md` | Manager and seller | Where the seller is versus plan and tenured peers, three actions, a manager opener, a success measure |
| `output/assessments.csv` | Analysts | Every ratio behind the call |

## How it decides

1. **Ramp plan** (`ramp/config.py`): activity, pipeline and bookings a new seller should show by ramp
   week, reaching full productivity around week 12. Bookings cannot start until one sales cycle has passed.
2. **Leading indicators**: last four weeks of meetings and pipeline versus plan, plus the share of
   opportunities with two or more contacts.
3. **Diagnosis** reports the earliest broken link, because problems cascade:
   low activity, then weak pipeline creation, then single threading, then poor conversion.
4. **Honest timing**: no call before ramp week 4, and no conversion call until bookings have had
   time to mature (one sales cycle plus four weeks).
5. **Impact**: an estimate of planned bookings over the next 90 days multiplied by the shortfall. It is
   an estimate from the plan, not a forecast.

## Results

Each seed builds a new fictional company with 40 new sellers, 16 of whom have a planted problem
(4 of each type). Thresholds were set before running and were not tuned on these seeds.

| Seed | Flagged | Precision | Recall | Recall on judgeable sellers | Diagnosis accuracy |
|---:|---:|---:|---:|---:|---:|
| 42 | 15 | 100% | 94% | 100% | 100% |
| 7 | 16 | 100% | 100% | 100% | 100% |
| 99 | 16 | 94% | 94% | 100% | 100% |
| 2026 | 15 | 100% | 94% | 100% | 100% |

Every miss was a poor-conversion seller who was too early for bookings to show the problem (weeks 7
to 9 in a 6 to 10 week cycle). The coach rated them on track and noted that conversion could not yet
be judged. One false alarm appeared across all four seeds (a healthy week 12 seller flagged for conversion
after an unlucky run of deals).

## Read this before trusting the numbers

- **I wrote the data and the detector.** The planted problems are clean, single-cause cases built
  from the same ramp plan the coach uses. Real sellers often have several issues at once, and these
  scores say nothing about real accuracy. Expect worse on real data.
- **The ramp plan is an assumption.** Real ramp curves, quotas, win rates, cycle lengths and
  coverage ratios differ by company. Replace `ramp/config.py` with your own before using it.
- **Synthetic noise is mild.** Real activity and CRM data has missing logging, territory changes,
  inherited pipeline, leave and seasonality. None of that is modeled.
- **The conversion call is slow by design.** It is the one problem the coach cannot see early. A
  manager should still look at young sellers' deal quality directly.
- **Coaching content is generic.** The playbook is a sensible starting point. It does not replace a
  manager's knowledge of the person.
- **Synthetic data only.** Do not run this on real CRM data without the right approval.

## Where this goes next

The same Meridian data can feed a company-level diagnostic (leakage, pipeline health, handoffs) so
that the ramp coach is one module of a broader sales transformation toolkit.
