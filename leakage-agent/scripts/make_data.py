"""Generate the synthetic billing data with leadforge, then plant labeled leakage.

Needs the leadforge package (pip install leadforge). Writes:
  data/clean/      four CSV tables, no leakage planted
  data/injected/   the same tables with leakage planted, plus ground_truth.csv
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from leakage.expected import TABLES, load_tables  # noqa: E402
from leakage.inject import inject, write_tables  # noqa: E402

SEED = 42


def main() -> None:
    exe = shutil.which("leadforge")
    if not exe:
        sys.exit("leadforge is not installed. Run: pip install leadforge")
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "bundle"
        subprocess.run(
            [exe, "generate", "--recipe", "b2b_saas_ltv_v1", "--seed", str(SEED), "--mode", "student_public",
             "--difficulty", "intermediate", "--n-leads", "500", "--out", str(bundle)],
            check=True,
        )
        clean = ROOT / "data" / "clean"
        clean.mkdir(parents=True, exist_ok=True)
        for name in TABLES:
            pd.read_parquet(bundle / "tables" / f"{name}.parquet").to_csv(clean / f"{name}.csv", index=False)
    injected, truth = inject(load_tables(clean), seed=7)
    out = ROOT / "data" / "injected"
    write_tables(injected, out)
    truth.to_csv(out / "ground_truth.csv", index=False)
    print(f"clean data: {clean}\ninjected data: {out}")
    print(truth.groupby("type").agg(cases=("customer_id", "count"), usd=("injected_usd", "sum")).round(0).to_string())


if __name__ == "__main__":
    main()
