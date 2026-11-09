"""Score the coach on several seeds. Thresholds were fixed before any run and not tuned on these seeds."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ramp.assess import assess_all
from ramp.generate import generate
from ramp.score import score

SEEDS = {42: "default", 7: "other", 99: "other", 2026: "other"}

if __name__ == "__main__":
    print("| Seed | Set | Troubled | Flagged | Precision | Recall | Recall (judgeable) | Diagnosis accuracy |")
    print("|---:|---|---:|---:|---:|---:|---:|---:|")
    for seed, name in SEEDS.items():
        reps, weekly, truth = generate(seed)
        s = score(assess_all(reps, weekly), truth, reps)
        print(f"| {seed} | {name} | {s['troubled']} | {s['flagged']} | {s['precision']:.0%} | {s['recall']:.0%} | "
              f"{s['detectable_recall']:.0%} | {s['diagnosis_accuracy']:.0%} |")
        for d in s["missed_detail"]:
            print(f"|  | missed | {d['rep_id']} {d['archetype']} week {d['ramp_weeks']} ({d['status']}) | | | | | |")
        for d in s["fp_detail"]:
            print(f"|  | false alarm | {d['rep_id']} as {d['diagnosis']} week {d['ramp_weeks']} | | | | | |")
