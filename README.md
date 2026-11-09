# Sales transformation toolkit

Three small tools that look for where a mid-sized sales organization loses revenue, time and ramp speed,
then turn what they find into ranked, owner-assigned fixes. They run on **Meridian**, a fictional
150-seller company with synthetic data. Every output is a draft for a person to review. Nothing is sent
or changed automatically.

> Independent personal project. It is not affiliated with or endorsed by any employer, and it uses no
> employer data, tools or metrics. All data is synthetic.

## The pieces

| Folder | Question it answers | Result on test data |
|---|---|---|
| [`diagnostic`](diagnostic) | Where is the sales process leaking, and what should we fix first? | 10 checks. Found 8 or 9 of 10 planted issues on four test companies, with 0 to 3 false alarms |
| [`ramp-coach`](ramp-coach) | Which new sellers are behind plan, and why? | 94 to 100% precision and recall on four test companies, 100% correct diagnosis on flagged sellers |
| [`leakage-agent`](leakage-agent) | Which contracted revenue was never billed or collected? | After adding realistic noise, 0 false positives on a holdout set at 88 to 100% recall |

The diagnostic reuses the ramp coach as one of its ten checks, which is why they live in one repo.

## Related experiments

Three scored prompt experiments, each on synthetic data with an answer key and a verifier. They test
whether a structured prompt beats a vague one for the same sales problems:

- [Pipeline brief](https://github.com/krystlekennedy1/ai-pipeline-brief-test): can an AI-written pipeline brief be trusted?
- [Lead-to-cash handoff](https://github.com/krystlekennedy1/ai-lead-to-cash-handoff-test): where do closed-won deals lose time before kickoff?
- [New-rep ramp coach](https://github.com/krystlekennedy1/ai-new-rep-ramp-coach-test): which new reps need coaching, and which should be left alone?

The experiments test prompts. This toolkit is working code.

## What the diagnostic produces

A ranked report for sales leaders: the top five things to fix first, each with evidence, an estimated
dollar impact, a confidence score, an owner, an effort level and a first step. The checks cover untouched
pipeline, past-due close dates, repeated close date pushes, forecast bias, slow lead response,
unapproved discounts, late invoicing, won deals never invoiced, incomplete handoffs and new sellers
behind ramp. See [`diagnostic/output/diagnostic_report.md`](diagnostic/output/diagnostic_report.md) for a sample.

## Quick start

Python 3.10 or newer.

```bash
pip install pandas numpy pytest

cd diagnostic   && python -m diag.run --seed 42 --out output && python -m pytest -q && cd ..
cd ramp-coach   && python -m ramp.generate --seed 42 --out data/meridian && python -m ramp.run && python -m pytest -q && cd ..
cd leakage-agent && pip install -r requirements.txt && python -m leakage.run --data data/noisy_b --out output --fresh && python -m pytest -q
```

Each folder has its own README with method, scoring and limits.

## How these were tested

Each tool is scored against problems planted in synthetic data, on several random seeds, plus clean
control companies with nothing planted to count false alarms. Misses and changes made after seeing results
are listed in each README. Where the tests found weak spots (small samples, subtle forecast bias, tiny
invoicing leaks), the READMEs say so.

## Limits you should know about

- **I wrote both the data and the detectors.** Planted problems are cleaner than real ones. Expect lower
  accuracy on real data. These scores show the logic works, not that it will work on your company.
- **Dollar figures rest on stated assumptions** (win rate, delay cost, rework cost) that you should replace
  with your own. Impacts are in different units, so the ranking is a starting order for discussion.
- **A finding says where to look, not why.**
- **Synthetic data only.** Do not run these on real CRM, billing or HR data without the right approval.

## Credits

The leakage agent's test data is generated with [leadforge](https://github.com/leadforge-dev/leadforge)
(MIT). Its detect, diagnose, decide, guardrail and audit structure follows a pattern seen in a public
hackathon project, but no code was copied from it.

## License

[MIT](LICENSE).
