"""Expected billing, derived from contract state.

A customer's expected monthly amount is their starting MRR, stepped up by each
expansion event and zeroed by a churn event. Every invoice is compared against
the step in effect on its invoice date.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import DEFAULT, Config

BILLING_CYCLE_DAYS = 28
MAX_NORMAL_GAP_DAYS = 35

TABLES = ("customers", "subscription_events", "invoices", "accounts")
# Optional context tables. When a file is missing the table is loaded empty.
OPTIONAL = {
    "discount_approvals": ["customer_id", "approved_pct", "effective_from", "approver"],
    "credit_memos": ["invoice_id", "customer_id", "credit_usd", "reason"],
}


def load_tables(directory) -> dict[str, pd.DataFrame]:
    d = Path(directory)
    tables = {name: pd.read_csv(d / f"{name}.csv") for name in TABLES}
    for name, cols in OPTIONAL.items():
        f = d / f"{name}.csv"
        tables[name] = pd.read_csv(f) if f.exists() else pd.DataFrame(columns=cols)
    tables["customers"]["customer_start_at"] = pd.to_datetime(tables["customers"]["customer_start_at"])
    tables["subscription_events"]["event_timestamp"] = pd.to_datetime(
        tables["subscription_events"]["event_timestamp"]
    )
    tables["invoices"]["invoice_date"] = pd.to_datetime(tables["invoices"]["invoice_date"])
    return tables


def mrr_steps(customers: pd.DataFrame, events: pd.DataFrame, cfg: Config = DEFAULT) -> pd.DataFrame:
    """One row per contract state: start, each expansion, and churn."""
    start = pd.DataFrame(
        {
            "customer_id": customers["customer_id"],
            "effective_date": customers["customer_start_at"],
            "event_date": pd.NaT,
            "mrr": customers["initial_mrr"].astype(float),
            "prior_mrr": float("nan"),
            "step_type": "start",
        }
    )
    kinds = ["expansion", "churn"] + (["downgrade"] if cfg.handle_downgrades else [])
    changed = events[events["event_type"].isin(kinds)]
    # Billing rule: a change made on an invoice date applies from the next invoice, so a change
    # takes effect the day after the event. An expansion gets a longer grace period, because
    # billing is often a few days behind and a late expansion is not yet leakage. Downgrades and
    # churn apply at once, so a customer is never billed more than they are due.
    lag = np.where(changed["event_type"] == "expansion", cfg.expansion_grace_days, 1)
    changes = pd.DataFrame(
        {
            "customer_id": changed["customer_id"],
            "effective_date": changed["event_timestamp"] + pd.to_timedelta(lag, unit="D"),
            "event_date": changed["event_timestamp"],
            "mrr": changed["mrr_after"].astype(float),
            "prior_mrr": changed["mrr_before"].astype(float),
            "step_type": changed["event_type"],
        }
    )
    steps = pd.concat([start, changes], ignore_index=True)
    return steps.sort_values(["effective_date", "customer_id"]).reset_index(drop=True)


def attach_expected(invoices: pd.DataFrame, steps: pd.DataFrame) -> pd.DataFrame:
    """Add expected_amount, prior_mrr, step_type and effective_date to each invoice."""
    # Normalize the join key so an empty or differently typed events table cannot break the merge.
    inv = invoices.assign(customer_id=invoices["customer_id"].astype(str)).sort_values("invoice_date")
    steps = steps.assign(customer_id=steps["customer_id"].astype(str))
    merged = pd.merge_asof(
        inv,
        steps,
        left_on="invoice_date",
        right_on="effective_date",
        by="customer_id",
        direction="backward",
    )
    merged = merged.rename(columns={"mrr": "expected_amount"})
    return merged.sort_values(["customer_id", "invoice_date"]).reset_index(drop=True)
