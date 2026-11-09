"""Score detections against the injected ground truth."""
from __future__ import annotations

import pandas as pd

INJECTED_TYPES = ["unbilled_expansion", "silent_discount", "billing_gap"]


def score(findings: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for kind in INJECTED_TYPES:
        f = findings[findings["type"] == kind]
        g = truth[truth["type"] == kind]
        hit = set(f["customer_id"]) & set(g["customer_id"])
        injected = g[g["customer_id"].isin(hit)]["injected_usd"].sum()
        found = f[f["customer_id"].isin(hit)]["impact_usd"].sum()
        rows.append(
            dict(
                type=kind,
                planted=len(g),
                flagged=len(f),
                correct=len(hit),
                precision=len(hit) / len(f) if len(f) else float("nan"),
                recall=len(hit) / len(g) if len(g) else float("nan"),
                planted_usd=round(float(g["injected_usd"].sum())),
                estimated_usd=round(float(found)),
                dollar_accuracy=(found / injected) if injected else float("nan"),
            )
        )
    return pd.DataFrame(rows)
