# Revenue leakage run (synthetic data, as of 2025-02-04)

Findings: 142. Estimated impact: $1,606,773.

## By type

| Type | Findings | Impact (USD) |
|---|---:|---:|
| billing_gap | 52 | 570,378 |
| silent_discount | 37 | 183,644 |
| unbilled_expansion | 28 | 518,391 |
| unrecovered_failure | 1 | 5,836 |
| write_off | 24 | 328,524 |

## By guardrail outcome

| Status | Findings | Impact (USD) |
|---|---:|---:|
| deferred | 57 | 173,756 |
| drafted | 50 | 585,015 |
| escalated | 35 | 848,002 |

## Top 10 by impact

| Customer | Type | Impact (USD) | Status |
|---|---|---:|---|
| Company acct_000448 | unbilled_expansion | 104,033 | escalated |
| Company acct_000142 | unbilled_expansion | 54,839 | escalated |
| Company acct_000090 | unbilled_expansion | 49,126 | escalated |
| Company acct_000063 | billing_gap | 47,756 | escalated |
| Company acct_000469 | unbilled_expansion | 46,736 | escalated |
| Company acct_000472 | write_off | 45,694 | escalated |
| Company acct_000489 | billing_gap | 43,490 | escalated |
| Company acct_000247 | billing_gap | 37,426 | escalated |
| Company acct_000335 | unbilled_expansion | 37,002 | escalated |
| Company acct_000356 | billing_gap | 36,698 | escalated |

## Score against planted leakage

| Type | Planted | Flagged | Correct | Precision | Recall | Planted USD | Estimated USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| unbilled_expansion | 32 | 28 | 28 | 100% | 88% | 601,192 | 518,391 |
| silent_discount | 37 | 37 | 37 | 100% | 100% | 189,369 | 183,644 |
| billing_gap | 52 | 52 | 52 | 100% | 100% | 655,236 | 570,378 |
