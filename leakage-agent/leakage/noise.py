"""Realistic billing noise: variation that can look like leakage but is not.

Discrete noise is applied to separate customers, and each case is recorded in noise_truth so
false positives can be traced to a cause:
  proration           first invoice after an expansion is a partial-period amount
  approved_discount   a discount that has a deal desk approval on record
  credit_memo         a one-off service credit on a single invoice, with a credit memo record
  pause               the customer paused, so invoices were skipped, with pause and resume events
  downgrade           a recorded downgrade, with invoices following the lower MRR
  duplicate_invoice   the same invoice appears twice
Global noise touches every customer:
  late invoices       about 20 percent of invoices are dated 1 to 9 days late
  rounding            about 30 percent of invoice amounts move by up to 0.2 percent

Leakage is planted afterwards on customers that have no discrete noise, then rounding is applied
last, so planted leakage also carries rounding noise.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import LEGACY
from .expected import OPTIONAL, attach_expected, mrr_steps
from .inject import inject


@dataclass(frozen=True)
class NoiseRates:
    proration: float = 0.20          # share of customers that have an expansion
    approved_discount: float = 0.04
    credit_memo: float = 0.04
    pause: float = 0.03
    downgrade: float = 0.05
    duplicate: float = 0.02
    late_share: float = 0.20
    rounding_share: float = 0.30


def _sub(cust: str) -> str:
    return "sub_" + cust.split("_")[1]


def add_noise(tables: dict[str, pd.DataFrame], seed: int = 11, rates: NoiseRates = NoiseRates()):
    rng = np.random.default_rng(seed)
    events = tables["subscription_events"]
    inv_exp = attach_expected(tables["invoices"], mrr_steps(tables["customers"], events, LEGACY))
    groups = {c: g.reset_index(drop=True) for c, g in inv_exp.groupby("customer_id")}
    expanders = set(events.loc[events["event_type"] == "expansion", "customer_id"])
    new_amt: dict[str, int] = {}
    drop: set[str] = set()
    new_events: list[dict] = []
    approvals: list[dict] = []
    credits: list[dict] = []
    dups: list[pd.Series] = []
    noise: list[dict] = []
    used: set[str] = set()

    def ev(cust, ts, kind, before, after):
        new_events.append(dict(event_id=f"noise_ev_{len(new_events):05d}", subscription_id=_sub(cust),
                               customer_id=cust, event_timestamp=ts, event_type=kind,
                               mrr_before=before, mrr_after=after, contract_term_months_new=np.nan))

    # proration
    exp_events = events[events["event_type"] == "expansion"].sort_values(["customer_id", "event_timestamp"])
    for cust, e in exp_events.groupby("customer_id"):
        if cust in used or rng.random() > rates.proration:
            continue
        pick = e.iloc[int(rng.integers(len(e)))]
        rows = groups[cust][(groups[cust]["event_date"] == pick["event_timestamp"])
                            & (groups[cust]["step_type"] == "expansion")]
        if len(rows) < 2:
            continue
        first = rows.iloc[0]
        frac = float(rng.uniform(0.3, 0.8))
        new_amt[first["invoice_id"]] = int(round(pick["mrr_before"] + frac * (pick["mrr_after"] - pick["mrr_before"])))
        noise.append(dict(kind="proration", customer_id=cust, detail=first["invoice_id"]))
        used.add(cust)

    # approved discount
    for cust, g in groups.items():
        if cust in used or len(g) < 4 or rng.random() > rates.approved_discount:
            continue
        s = int(rng.integers(1, len(g) - 1))
        d = float(rng.choice([0.05, 0.10, 0.15, 0.20]))
        tail = g.iloc[s:]
        for iid, amt in zip(tail["invoice_id"], (tail["expected_amount"] * (1 - d)).round().astype(int)):
            new_amt[iid] = int(amt)
        approvals.append(dict(customer_id=cust, approved_pct=d,
                              effective_from=str((tail["invoice_date"].iloc[0] - pd.Timedelta(days=5)).date()),
                              approver="deal_desk"))
        noise.append(dict(kind="approved_discount", customer_id=cust, detail=f"{d:.0%}"))
        used.add(cust)

    # credit memo
    for cust, g in groups.items():
        if cust in used or len(g) < 3 or rng.random() > rates.credit_memo:
            continue
        r = g.iloc[int(rng.integers(1, len(g)))]
        amt = int(round(r["expected_amount"] * (1 - float(rng.uniform(0.2, 0.6)))))
        new_amt[r["invoice_id"]] = amt
        credits.append(dict(invoice_id=r["invoice_id"], customer_id=cust,
                            credit_usd=float(r["expected_amount"] - amt), reason="service_credit"))
        noise.append(dict(kind="credit_memo", customer_id=cust, detail=r["invoice_id"]))
        used.add(cust)

    # pause
    for cust, g in groups.items():
        if cust in used or len(g) < 6 or rng.random() > rates.pause:
            continue
        k = 2
        s = int(rng.integers(2, len(g) - k - 1))
        gone = g.iloc[s:s + k]
        drop.update(gone["invoice_id"])
        mrr = float(g.iloc[s - 1]["expected_amount"])
        ev(cust, g.iloc[s - 1]["invoice_date"] + pd.Timedelta(days=3), "pause", mrr, mrr)
        ev(cust, g.iloc[s + k]["invoice_date"] - pd.Timedelta(days=2), "resume", mrr, mrr)
        noise.append(dict(kind="pause", customer_id=cust, detail=";".join(gone["invoice_id"])))
        used.add(cust)

    # downgrade (customers with no expansion events, so the new MRR is unambiguous)
    for cust, g in groups.items():
        if cust in used or cust in expanders or len(g) < 5 or rng.random() > rates.downgrade:
            continue
        s = int(rng.integers(2, len(g) - 1))
        old = float(g.iloc[s]["expected_amount"])
        new = int(round(old * (1 - float(rng.uniform(0.2, 0.5)))))
        ev(cust, g.iloc[s]["invoice_date"] - pd.Timedelta(days=7), "downgrade", old, float(new))
        for iid in g.iloc[s:]["invoice_id"]:
            new_amt[iid] = new
        noise.append(dict(kind="downgrade", customer_id=cust, detail=f"{old:.0f}->{new}"))
        used.add(cust)

    # duplicate invoice
    inv = tables["invoices"]
    for cust, g in groups.items():
        if cust in used or rng.random() > rates.duplicate:
            continue
        r = g.iloc[int(rng.integers(len(g)))]
        row = inv[inv["invoice_id"] == r["invoice_id"]].iloc[0].copy()
        row["invoice_id"] = "dup_" + row["invoice_id"]
        dups.append(row)
        noise.append(dict(kind="duplicate_invoice", customer_id=cust, detail=row["invoice_id"]))
        used.add(cust)

    out = {k: v.copy() for k, v in tables.items()}
    invoices = out["invoices"]
    mask = invoices["invoice_id"].isin(new_amt)
    invoices.loc[mask, "amount_usd"] = invoices.loc[mask, "invoice_id"].map(new_amt)
    invoices = invoices[~invoices["invoice_id"].isin(drop)]
    if dups:
        invoices = pd.concat([invoices, pd.DataFrame(dups)], ignore_index=True)

    # late invoices: positive shifts only, so invoice order is preserved
    late = rng.random(len(invoices)) < rates.late_share
    shift = np.where(rng.random(len(invoices)) < 0.8, rng.integers(1, 4, len(invoices)), rng.integers(4, 10, len(invoices)))
    invoices["invoice_date"] = invoices["invoice_date"] + pd.to_timedelta(np.where(late, shift, 0), unit="D")
    out["invoices"] = invoices.sort_values(["customer_id", "invoice_date"]).reset_index(drop=True)

    if new_events:
        extra = pd.DataFrame(new_events)
        extra["event_timestamp"] = pd.to_datetime(extra["event_timestamp"])
        out["subscription_events"] = pd.concat([out["subscription_events"], extra], ignore_index=True)
    out["discount_approvals"] = pd.DataFrame(approvals, columns=OPTIONAL["discount_approvals"])
    out["credit_memos"] = pd.DataFrame(credits, columns=OPTIONAL["credit_memos"])
    return out, pd.DataFrame(noise, columns=["kind", "customer_id", "detail"])


def add_rounding(tables: dict[str, pd.DataFrame], seed: int, rates: NoiseRates = NoiseRates()):
    rng = np.random.default_rng(seed)
    out = {k: v.copy() for k, v in tables.items()}
    inv = out["invoices"]
    hit = rng.random(len(inv)) < rates.rounding_share
    factor = 1 + rng.uniform(-0.002, 0.002, len(inv))
    inv["amount_usd"] = np.where(hit, (inv["amount_usd"] * factor).round(), inv["amount_usd"]).astype(int)
    return out


def build_noisy(clean: dict[str, pd.DataFrame], noise_seed: int, leak_seed: int):
    """Noise first, then leakage on noise-free customers, then rounding on everything."""
    noisy, noise_truth = add_noise(clean, noise_seed)
    planted, truth = inject(noisy, seed=leak_seed, exclude=set(noise_truth["customer_id"]),
                            rate_unbilled=0.15, rate_discount=0.05, rate_gap=0.07)
    return add_rounding(planted, noise_seed + 1000), truth, noise_truth
