# Noise evaluation

P is precision and R is recall, against leakage planted in each dataset. A false positive is a finding of a planted type on a customer that has no such planted leakage. Native write-offs from the data generator are real and are excluded. Set A was used to tune the detectors. Set B was scored once the detectors were final.

## Before and after

| Variant | False positives | Reached a draft or escalation | Unbilled expansion (P / R) | Silent discount (P / R) | Billing gap (P / R) |
|---|---:|---:|---|---|---|
| noisy_a, first version | 868 | 63 | 73% / 87% | 20% / 100% | 6% / 100% |
| noisy_a, improved | 0 | 0 | 100% / 84% | 100% / 100% | 100% / 100% |
| noisy_b, first version | 872 | 65 | 65% / 88% | 18% / 100% | 7% / 100% |
| noisy_b, improved | 0 | 0 | 100% / 88% | 100% / 100% | 100% / 100% |

### noisy_a, first version

| Type | Planted | Flagged | Correct | Precision | Recall | $ accuracy |
|---|---:|---:|---:|---:|---:|---:|
| unbilled_expansion | 31 | 37 | 27 | 73% | 87% | 67% |
| silent_discount | 41 | 209 | 41 | 20% | 100% | 100% |
| billing_gap | 47 | 766 | 47 | 6% | 100% | 135% |

False positives: 868

| Cause | Flagged as | Count | Reached a draft or escalation |
|---|---|---:|---:|
| unexplained (late invoices or rounding) | billing_gap | 507 | 37 |
| proration | silent_discount | 54 | 0 |
| proration | billing_gap | 38 | 3 |
| credit_memo | silent_discount | 38 | 0 |
| approved_discount | silent_discount | 36 | 1 |
| pause | billing_gap | 34 | 3 |
| type confusion (planted unbilled_expansion) | billing_gap | 25 | 3 |
| downgrade | silent_discount | 22 | 5 |
| credit_memo | billing_gap | 21 | 1 |
| type confusion (planted silent_discount) | billing_gap | 21 | 3 |
| approved_discount | billing_gap | 19 | 1 |
| downgrade | billing_gap | 17 | 2 |
| type confusion (planted unbilled_expansion) | silent_discount | 14 | 3 |
| duplicate_invoice | billing_gap | 8 | 1 |
| unexplained (late invoices or rounding) | unbilled_expansion | 3 | 0 |
| unexplained (late invoices or rounding) | silent_discount | 3 | 0 |
| proration | unbilled_expansion | 3 | 0 |
| duplicate_invoice | unbilled_expansion | 2 | 0 |
| approved_discount | unbilled_expansion | 1 | 0 |
| credit_memo | unbilled_expansion | 1 | 0 |
| type confusion (planted billing_gap) | silent_discount | 1 | 0 |

### noisy_a, improved

| Type | Planted | Flagged | Correct | Precision | Recall | $ accuracy |
|---|---:|---:|---:|---:|---:|---:|
| unbilled_expansion | 31 | 26 | 26 | 100% | 84% | 96% |
| silent_discount | 41 | 41 | 41 | 100% | 100% | 92% |
| billing_gap | 47 | 47 | 47 | 100% | 100% | 92% |

False positives: 0

### noisy_b, first version

| Type | Planted | Flagged | Correct | Precision | Recall | $ accuracy |
|---|---:|---:|---:|---:|---:|---:|
| unbilled_expansion | 32 | 43 | 28 | 65% | 88% | 76% |
| silent_discount | 37 | 207 | 37 | 18% | 100% | 100% |
| billing_gap | 52 | 760 | 52 | 7% | 100% | 113% |

False positives: 872

| Cause | Flagged as | Count | Reached a draft or escalation |
|---|---|---:|---:|
| unexplained (late invoices or rounding) | billing_gap | 518 | 42 |
| credit_memo | silent_discount | 48 | 0 |
| proration | silent_discount | 43 | 0 |
| approved_discount | silent_discount | 34 | 0 |
| pause | billing_gap | 33 | 9 |
| credit_memo | billing_gap | 29 | 2 |
| proration | billing_gap | 29 | 3 |
| type confusion (planted silent_discount) | billing_gap | 20 | 1 |
| type confusion (planted unbilled_expansion) | billing_gap | 19 | 0 |
| type confusion (planted unbilled_expansion) | silent_discount | 18 | 1 |
| downgrade | silent_discount | 18 | 3 |
| approved_discount | billing_gap | 17 | 0 |
| downgrade | billing_gap | 13 | 0 |
| unexplained (late invoices or rounding) | unbilled_expansion | 10 | 1 |
| duplicate_invoice | billing_gap | 9 | 3 |
| unexplained (late invoices or rounding) | silent_discount | 7 | 0 |
| type confusion (planted billing_gap) | unbilled_expansion | 3 | 0 |
| proration | unbilled_expansion | 2 | 0 |
| duplicate_invoice | silent_discount | 1 | 0 |
| type confusion (planted billing_gap) | silent_discount | 1 | 0 |

### noisy_b, improved

| Type | Planted | Flagged | Correct | Precision | Recall | $ accuracy |
|---|---:|---:|---:|---:|---:|---:|
| unbilled_expansion | 32 | 28 | 28 | 100% | 88% | 90% |
| silent_discount | 37 | 37 | 37 | 100% | 100% | 97% |
| billing_gap | 52 | 52 | 52 | 100% | 100% | 87% |

False positives: 0

## Ablation on holdout set B

Each row turns off one improvement and leaves the rest on.

| Variant | False positives | Reached a draft or escalation | Unbilled expansion (P / R) | Silent discount (P / R) | Billing gap (P / R) |
|---|---:|---:|---|---|---|
| all improvements | 0 | 0 | 100% / 88% | 100% / 100% | 100% / 100% |
| no lateness tolerance (35 day gap limit) | 659 | 58 | 100% / 88% | 100% / 100% | 7% / 100% |
| no expansion grace period | 26 | 5 | 57% / 100% | 95% / 100% | 100% / 100% |
| no amount tolerance when classifying | 24 | 4 | 100% / 75% | 61% / 100% | 100% / 100% |
| no downgrade handling | 18 | 8 | 100% / 88% | 67% / 100% | 100% / 100% |
| no pause handling | 22 | 15 | 100% / 88% | 100% / 100% | 70% / 100% |
| no proration rule | 33 | 0 | 100% / 88% | 53% / 100% | 100% / 100% |
| no approvals table | 34 | 2 | 100% / 88% | 52% / 100% | 100% / 100% |
| no credit memo table | 47 | 0 | 100% / 88% | 44% / 100% | 100% / 100% |
| no event skew tolerance | 2 | 1 | 100% / 88% | 100% / 100% | 96% / 100% |

## Missing records on holdout set B

Half of the discount approval and credit memo records are removed, as in real data where approvals and credits are not always logged.

| Variant | False positives | Reached a draft or escalation | Unbilled expansion (P / R) | Silent discount (P / R) | Billing gap (P / R) |
|---|---:|---:|---|---|---|
| improved, half of records missing | 43 | 1 | 100% / 88% | 46% / 100% | 100% / 100% |

| Cause | Guardrail outcome | Count |
|---|---|---:|
| credit_memo | needs_review | 26 |
| approved_discount | deferred | 16 |
| approved_discount | drafted | 1 |

## Original datasets without noise

| Variant | False positives | Reached a draft or escalation | Unbilled expansion (P / R) | Silent discount (P / R) | Billing gap (P / R) |
|---|---:|---:|---|---|---|
| injected only, first version | 0 | 0 | 100% / 100% | 100% / 100% | 100% / 100% |
| injected only, improved | 0 | 0 | 100% / 86% | 100% / 100% | 100% / 100% |

Clean data with no planted leakage, improved detectors: {'write_off': 24, 'unrecovered_failure': 1}
