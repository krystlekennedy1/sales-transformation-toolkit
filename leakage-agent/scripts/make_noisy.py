"""Build the noisy datasets from data/clean.

  data/noisy_a   tuning set (noise seed 11, leakage seed 7)
  data/noisy_b   holdout set (noise seed 23, leakage seed 9), never used to tune a detector

Each folder holds the billing tables, discount_approvals.csv, credit_memos.csv, ground_truth.csv
(planted leakage) and noise_truth.csv (planted noise that is not leakage).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from leakage.expected import load_tables  # noqa: E402
from leakage.inject import write_tables  # noqa: E402
from leakage.noise import build_noisy  # noqa: E402

SETS = {"noisy_a": (11, 7), "noisy_b": (23, 9)}


def main() -> None:
    clean = load_tables(ROOT / "data" / "clean")
    for name, (noise_seed, leak_seed) in SETS.items():
        tables, truth, noise_truth = build_noisy(clean, noise_seed, leak_seed)
        out = ROOT / "data" / name
        write_tables(tables, out)
        truth.to_csv(out / "ground_truth.csv", index=False)
        noise_truth.to_csv(out / "noise_truth.csv", index=False)
        print(f"\n{name}: {len(tables['invoices'])} invoices")
        print("planted leakage:", truth.groupby("type").size().to_dict())
        print("planted noise:  ", noise_truth.groupby("kind").size().to_dict())


if __name__ == "__main__":
    main()
