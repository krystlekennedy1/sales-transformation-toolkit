"""Detectors. Each returns one row per finding with an impact estimate in USD."""
from __future__ import annotations

import pandas as pd

from .config import DEFAULT, Config
from .expected import BILLING_CYCLE_DAYS

COLUMNS = ["finding_id", "customer_id", "type", "first_date", "last_date", "n_invoices", "impact_usd", "evidence"]
APPROVAL_MATCH_PCT = 0.015  # an approved discount matches if the billed discount is within 1.5 points of it


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COLUMNS)


def _short_invoices(inv_exp: pd.DataFrame, cfg: Config, credits: pd.DataFrame | None) -> pd.DataFrame:
    """Invoices below expected, after removing shortfalls that have an ordinary explanation."""
    d = inv_exp.copy()
    d["shortfall"] = d["expected_amount"] - d["amount_usd"]
    is_short = d["shortfall"] > d["expected_amount"] * cfg.short_tol

    if cfg.detect_proration:
        # A partial first invoice after an expansion, followed by a full one, is proration.
        pos = d.groupby(["customer_id", "effective_date"]).cumcount()
        nxt_amount = d.groupby("customer_id")["amount_usd"].shift(-1)
        nxt_expected = d.groupby("customer_id")["expected_amount"].shift(-1)
        prorated = (
            (d["step_type"] == "expansion")
            & (pos == 0)
            & (d["amount_usd"] > d["prior_mrr"] * (1 + cfg.match_tol))
            & (d["amount_usd"] < d["expected_amount"] * (1 - cfg.short_tol))
            & ((nxt_amount - nxt_expected).abs() <= cfg.match_tol * nxt_expected)
            & (nxt_expected == d["expected_amount"])
        )
        is_short &= ~prorated

    if cfg.use_credits and credits is not None and not credits.empty:
        credited = d["invoice_id"].map(credits.groupby("invoice_id")["credit_usd"].sum()).fillna(0.0)
        is_short &= ~(credited >= d["shortfall"] - 0.01 * d["expected_amount"])

    return d[is_short].copy()


def detect_underbilling(inv_exp: pd.DataFrame, cfg: Config = DEFAULT, approvals: pd.DataFrame | None = None,
                        credits: pd.DataFrame | None = None) -> pd.DataFrame:
    """Invoices below the expected amount.

    Short invoices that match the pre-expansion MRR are an unbilled expansion. Any other shortfall
    is a silent discount, unless an approval on record matches it.
    """
    short = _short_invoices(inv_exp, cfg, credits)
    unbilled = (short["step_type"] == "expansion") & (
        (short["amount_usd"] - short["prior_mrr"]).abs() <= cfg.match_tol * short["prior_mrr"]
    )
    short["kind"] = unbilled.map({True: "unbilled_expansion", False: "silent_discount"})
    rows = []
    for (cust, kind), g in short.groupby(["customer_id", "kind"]):
        pct = g["shortfall"] / g["expected_amount"]
        rows.append(
            dict(
                finding_id=f"{kind}:{cust}",
                customer_id=cust,
                type=kind,
                first_date=g["invoice_date"].min(),
                last_date=g["invoice_date"].max(),
                n_invoices=len(g),
                impact_usd=float(g["shortfall"].sum()),
                evidence=dict(
                    avg_shortfall_pct=round(float(pct.mean()), 4),
                    pct_spread=round(float(pct.std(ddof=0)), 4),
                    expected_amount=float(g["expected_amount"].iloc[0]),
                    billed_amount=float(g["amount_usd"].iloc[0]),
                    step_date=str(g["event_date"].min().date()) if g["event_date"].notna().any()
                    else str(g["effective_date"].min().date()),
                ),
            )
        )
    frame = _frame(rows)
    if cfg.use_approvals and approvals is not None and not approvals.empty and not frame.empty:
        approved = approvals.groupby("customer_id")["approved_pct"].apply(list).to_dict()
        keep = [
            not (r.type == "silent_discount"
                 and any(abs(r.evidence["avg_shortfall_pct"] - p) <= APPROVAL_MATCH_PCT
                         for p in approved.get(r.customer_id, [])))
            for r in frame.itertuples()
        ]
        frame = frame[keep].reset_index(drop=True)
    return frame


def detect_billing_gaps(inv_exp: pd.DataFrame, events: pd.DataFrame, as_of: pd.Timestamp,
                        cfg: Config = DEFAULT) -> pd.DataFrame:
    """Missing invoices: a gap longer than the normal cycle plus lateness, or billing that stopped
    for a customer who has neither churned nor paused."""
    max_gap = cfg.max_gap_days
    skew = pd.Timedelta(days=cfg.event_skew_days)
    churned = set(events.loc[events["event_type"] == "churn", "customer_id"])
    failures = events[events["event_type"] == "payment_failure"].groupby("customer_id")["event_timestamp"].apply(list)
    pauses = events[events["event_type"] == "pause"].groupby("customer_id")["event_timestamp"].apply(list)
    resumes = events[events["event_type"] == "resume"].groupby("customer_id")["event_timestamp"].apply(list)
    rows = []
    for cust, g in inv_exp.groupby("customer_id"):
        dates = g["invoice_date"].tolist()
        expected = g["expected_amount"].tolist()
        fail_dates = failures.get(cust, [])
        pause_dates = pauses.get(cust, []) if cfg.handle_pauses else []
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i - 1]).days
            if gap <= max_gap:
                continue
            if any(dates[i - 1] - skew <= p <= dates[i] + skew for p in pause_dates):
                continue  # the customer paused, so skipped invoices are expected
            missing = max(1, gap // BILLING_CYCLE_DAYS - 1)
            near_failure = any(dates[i - 1] <= f <= dates[i] for f in fail_dates)
            rows.append(
                dict(
                    finding_id=f"billing_gap:{cust}:{dates[i - 1]:%Y%m%d}",
                    customer_id=cust,
                    type="billing_gap",
                    first_date=dates[i - 1],
                    last_date=dates[i],
                    n_invoices=missing,
                    impact_usd=float(missing * expected[i - 1]),
                    evidence=dict(gap_days=gap, missing_invoices=missing, trailing=False,
                                  near_payment_failure=near_failure, monthly_amount=float(expected[i - 1])),
                )
            )
        since_last = (as_of - dates[-1]).days
        still_paused = bool(pause_dates) and max(pause_dates) >= dates[-1] and not any(
            r >= max(pause_dates) for r in resumes.get(cust, []))
        if cust not in churned and since_last > max_gap and not still_paused:
            missing = max(1, since_last // BILLING_CYCLE_DAYS)
            rows.append(
                dict(
                    finding_id=f"billing_gap:{cust}:{dates[-1]:%Y%m%d}",
                    customer_id=cust,
                    type="billing_gap",
                    first_date=dates[-1],
                    last_date=as_of,
                    n_invoices=missing,
                    impact_usd=float(missing * expected[-1]),
                    evidence=dict(gap_days=since_last, missing_invoices=missing, trailing=True,
                                  near_payment_failure=any(f >= dates[-1] for f in fail_dates),
                                  monthly_amount=float(expected[-1])),
                )
            )
    return _frame(rows)


def detect_write_offs(inv_exp: pd.DataFrame) -> pd.DataFrame:
    """Invoices written off, and invoices whose payment failed and was never recovered."""
    rows = []
    for status, kind in (("written_off", "write_off"), ("failed", "unrecovered_failure")):
        sel = inv_exp[inv_exp["payment_status"] == status]
        for cust, g in sel.groupby("customer_id"):
            rows.append(
                dict(
                    finding_id=f"{kind}:{cust}",
                    customer_id=cust,
                    type=kind,
                    first_date=g["invoice_date"].min(),
                    last_date=g["invoice_date"].max(),
                    n_invoices=len(g),
                    impact_usd=float(g["amount_usd"].sum()),
                    evidence=dict(statuses=status, invoice_ids=";".join(g["invoice_id"])),
                )
            )
    return _frame(rows)


def detect_all(inv_exp: pd.DataFrame, events: pd.DataFrame, as_of: pd.Timestamp, cfg: Config = DEFAULT,
               approvals: pd.DataFrame | None = None, credits: pd.DataFrame | None = None) -> pd.DataFrame:
    parts = [detect_underbilling(inv_exp, cfg, approvals, credits),
             detect_billing_gaps(inv_exp, events, as_of, cfg),
             detect_write_offs(inv_exp)]
    parts = [p for p in parts if not p.empty]
    if not parts:
        return _frame([])
    return pd.concat(parts, ignore_index=True)
