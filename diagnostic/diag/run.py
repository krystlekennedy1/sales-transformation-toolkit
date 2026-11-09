"""python -m diag.run --seed 42 --out output [--control]"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .checks import run_checks
from .config import AS_OF, DEFAULT
from .generate import generate
from .rank import rank
from .report import report


def diagnose(tables: dict, assumptions=DEFAULT) -> pd.DataFrame:
    tables = dict(tables, as_of=tables.get("as_of", AS_OF))
    return rank(run_checks(tables, assumptions))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="output")
    ap.add_argument("--control", action="store_true", help="company with no planted issues")
    a = ap.parse_args()
    t = generate(a.seed, planted=not a.control)
    ranked = diagnose(t)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(out / "findings.csv", index=False)
    (out / "diagnostic_report.md").write_text(report(ranked, DEFAULT))
    print(ranked[["rank", "check", "entity", "impact_usd", "confidence"]].to_string(index=False))


if __name__ == "__main__":
    main()
