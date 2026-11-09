# Revenue leakage agent (prototype)

Finds revenue that was contracted but never billed or collected, ranks it by dollar impact, applies
guardrails, and writes draft follow-ups for a human to review. It runs on synthetic data only and
never executes an action.

## Quick start

```bash
pip install -r requirements.txt
python -m leakage.run --data data/noisy_b --out output --fresh   # run the agent
python -m pytest -q                                              # 47 tests
python scripts/evaluate_noise.py                                 # rebuild NOISE_REPORT.md
python scripts/make_data.py && python scripts/make_noisy.py      # regenerate the data (needs leadforge)
```

Options: `--legacy` runs the first-version detector settings. `--ai` uses Claude to rewrite each
explanation (needs `pip install anthropic` and `ANTHROPIC_API_KEY`, otherwise it falls back to
rule-based text).

## What it does

| Step | File | What happens |
|---|---|---|
| Settings | `leakage/config.py` | Tolerances and switches. `LEGACY` reproduces the first version |
| Expected billing | `leakage/expected.py` | What each customer should be invoiced, from starting MRR, expansions, downgrades and churn |
| Detect | `leakage/detect.py` | Unbilled expansion, silent discount, billing gap, write-off, unrecovered failure |
| Diagnose | `leakage/diagnose.py` | Root cause, confidence, severity |
| Decide | `leakage/decide.py`, `leakage/guardrails.py` | Maps each type to an action, then hard limits decide what happens |
| Explain | `leakage/agent.py` | Rule text, or Claude text that is validated before use |
| Draft and audit | `leakage/drafts.py`, `leakage/audit.py` | Markdown drafts, append-only JSONL log |
| Test data | `leakage/inject.py`, `leakage/noise.py` | Plants labeled leakage and labeled look-alike noise |
| Score | `leakage/score.py`, `leakage/evaluate.py` | Precision and recall, with every false positive traced to its cause |

Guardrail outcomes: `drafted`, `escalated` (impact at or above $25,000, or write-offs), `needs_review`
(confidence below 0.60), `suppressed` (under $100, or already actioned in the last 14 days) and
`deferred` (more than 50 drafts in a run). Claude can only rewrite the explanation and next step. It
cannot change amounts, actions or guardrail results, and a reply that cites an amount not in the
finding is discarded.

## The data

| Folder | Contents |
|---|---|
| `data/clean` | leadforge `b2b_saas_ltv_v1` bundle: 1,500 customers, about 9,200 invoices |
| `data/injected` | Clean data plus labeled leakage, no noise |
| `data/noisy_a` | Tuning set: noise plus leakage on separate customers, with approvals, credit memos, pause and downgrade events |
| `data/noisy_b` | Holdout set from different seeds, scored once the detectors were final |

Noise that looks like leakage but is not: late invoices (20 percent of invoices dated 1 to 9 days
late), rounding, proration, approved discounts, credit memos, pauses, recorded downgrades and
duplicate invoices. Each case is recorded in `noise_truth.csv`.

## Results under noise

Precision (P) and recall (R) against planted leakage. Full tables, false positives by cause, an
ablation and a missing-records test are in `NOISE_REPORT.md`.

| Dataset | False positives | Unbilled expansion (P / R) | Silent discount (P / R) | Billing gap (P / R) |
|---|---:|---|---|---|
| noisy_b, first version | 872 | 65% / 88% | 18% / 100% | 7% / 100% |
| noisy_b, improved | 0 | 100% / 88% | 100% / 100% | 100% / 100% |

The first version found the real leakage but buried it in about 870 false alarms, mostly late
invoices read as missing ones. Each improvement was needed: removing any one brings back 2 to 659
false positives (see the ablation). Without noise, the first version scores 100 percent on all
three types and the improved version scores 86 percent recall on unbilled expansion.

## Read this before trusting the numbers

- **The holdout is not independent of the noise model.** Set B uses different random seeds, so it
  shows the detectors were not overfit to set A. It does not show the noise matches real billing,
  because I wrote both the noise and the fixes for it. Expect worse on real data.
- **The lateness limit is tuned to the noise.** Normal gaps are treated as up to 45 days because
  the noise delays invoices by at most 9 days. On real data, set `max_gap_days` from the observed
  distribution of invoice intervals.
- **The expansion grace period trades recall for precision.** An expansion billed within 10 days is
  not flagged. Without it, precision on unbilled expansion drops to 57 percent. The 88 percent
  recall is a snapshot effect: a shortfall that persists is flagged one billing cycle later.
- **The detectors depend on context records.** With half of the approvals and credit memos
  missing, silent discount precision falls to 46 percent. Single-invoice credit shortfalls land in
  `needs_review` because their confidence is low, but missing approvals on multi-invoice discounts
  still become drafts. In that test most were deferred only because the 50 draft cap was full.
- **Dollar estimates are approximate.** On noisy data they are 87 to 97 percent of the planted
  amounts, lowest for billing gaps because lateness makes gap length uncertain.
- **Billing assumptions.** A contract change made on an invoice date applies from the next invoice,
  downgrades apply at once, and the cycle is 28 or 35 days.
- **The Claude layer is tested with stubbed replies only.** It has not run against the live API.

## Using it on other data

Provide four CSVs. `customers`: customer_id, account_id, customer_start_at, initial_mrr.
`subscription_events`: customer_id, event_timestamp, event_type (expansion, downgrade, churn, pause,
resume, payment_failure), mrr_before, mrr_after. `invoices`: invoice_id, customer_id, invoice_date,
amount_usd, payment_status. `accounts`: account_id, company_name. Optional: `discount_approvals`
(customer_id, approved_pct, effective_from, approver) and `credit_memos` (invoice_id, customer_id,
credit_usd, reason). Keep it synthetic unless you have approval to use real data.

## Credits

Data comes from [leadforge](https://github.com/leadforge-dev/leadforge) (MIT). The detect, diagnose,
decide, guardrail and audit structure follows the pattern in the Revyn hackathon project, but no
Revyn code was copied.

## Sample output

`output/` holds a sample run on the holdout set. Only 5 of the draft files are kept here to keep the repo small. Re-run the quick start to regenerate them all.
