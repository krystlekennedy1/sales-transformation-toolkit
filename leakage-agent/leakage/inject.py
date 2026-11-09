"""Inject known revenue leakage into clean synthetic billing data.

Three leakage types are planted and labeled, so the detectors can be scored:
  unbilled_expansion  an expansion was contracted but invoices stayed at the old MRR
  silent_discount     invoices run 8 to 25 percent below contract with no approval record
  billing_gap         one or two invoices were never issued
Each customer receives at most one injected issue.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .config import LEGACY
from .expected import OPTIONAL, TABLES, attach_expected, load_tables, mrr_steps


def inject(tables: dict[str, pd.DataFrame], seed: int = 7, rate_unbilled: float = 0.12,
           rate_discount: float = 0.03, rate_gap: float = 0.03, exclude=None):
    rng = np.random.default_rng(seed)
    events = tables["subscription_events"]
    inv_exp = attach_expected(tables["invoices"], mrr_steps(tables["customers"], events, LEGACY))
    new_amounts: dict[str, int] = {}
    removed: set[str] = set()
    truth: list[dict] = []
    used: set[str] = set(exclude or ())

    # 1. unbilled expansion
    expansions = events[events["event_type"] == "expansion"].sort_values(["customer_id", "event_timestamp"])
    for cust, ev in expansions.groupby("customer_id"):
        if cust in used or rng.random() > rate_unbilled:
            continue
        pick = ev.iloc[int(rng.integers(len(ev)))]
        rows = inv_exp[(inv_exp["customer_id"] == cust) & (inv_exp["event_date"] == pick["event_timestamp"])
                       & (inv_exp["step_type"] == "expansion")]
        if rows.empty:
            continue
        lost = float((rows["expected_amount"] - pick["mrr_before"]).sum())
        for iid in rows["invoice_id"]:
            new_amounts[iid] = int(pick["mrr_before"])
        truth.append(dict(customer_id=cust, type="unbilled_expansion", injected_usd=lost,
                          n_invoices_affected=len(rows), invoice_ids=";".join(rows["invoice_id"])))
        used.add(cust)

    counts = inv_exp.groupby("customer_id").size()

    # 2. silent discount
    for cust in sorted(counts[counts >= 4].index):
        if cust in used or rng.random() > rate_discount:
            continue
        g = inv_exp[inv_exp["customer_id"] == cust].reset_index(drop=True)
        n = len(g)
        start = int(rng.integers(1, n - 1))
        pct = float(rng.uniform(0.08, 0.25))
        tail = g.iloc[start:]
        cut = (tail["expected_amount"] * (1 - pct)).round().astype(int)
        for iid, amt in zip(tail["invoice_id"], cut):
            new_amounts[iid] = int(amt)
        truth.append(dict(customer_id=cust, type="silent_discount",
                          injected_usd=float((tail["expected_amount"] - cut).sum()),
                          n_invoices_affected=len(tail), invoice_ids=";".join(tail["invoice_id"])))
        used.add(cust)

    # 3. billing gap
    for cust in sorted(counts[counts >= 5].index):
        if cust in used or rng.random() > rate_gap:
            continue
        g = inv_exp[inv_exp["customer_id"] == cust].reset_index(drop=True)
        n = len(g)
        k = int(rng.integers(1, 3))
        start = int(rng.integers(1, n - k))
        gone = g.iloc[start:start + k]
        removed.update(gone["invoice_id"])
        truth.append(dict(customer_id=cust, type="billing_gap",
                          injected_usd=float(gone["expected_amount"].sum()),
                          n_invoices_affected=len(gone), invoice_ids=";".join(gone["invoice_id"])))
        used.add(cust)

    out = {k: v.copy() for k, v in tables.items()}
    invoices = out["invoices"]
    mask = invoices["invoice_id"].isin(new_amounts)
    invoices.loc[mask, "amount_usd"] = invoices.loc[mask, "invoice_id"].map(new_amounts)
    out["invoices"] = invoices[~invoices["invoice_id"].isin(removed)].reset_index(drop=True)
    return out, pd.DataFrame(truth)


def write_tables(tables: dict[str, pd.DataFrame], directory) -> None:
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    for name in TABLES:
        tables[name].to_csv(d / f"{name}.csv", index=False)
    for name in OPTIONAL:
        if name in tables and not tables[name].empty:
            tables[name].to_csv(d / f"{name}.csv", index=False)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--clean", default="data/clean")
    p.add_argument("--out", default="data/injected")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    tables = load_tables(args.clean)
    injected, truth = inject(tables, seed=args.seed)
    write_tables(injected, args.out)
    truth.to_csv(Path(args.out) / "ground_truth.csv", index=False)
    print(f"Wrote injected data and ground truth to {args.out}")
    print(truth.groupby("type").agg(cases=("customer_id", "count"), usd=("injected_usd", "sum")).round(0).to_string())


if __name__ == "__main__":
    main()
