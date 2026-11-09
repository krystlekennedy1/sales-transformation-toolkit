"""Score the diagnostic on planted companies and clean controls, then stress the dollar assumptions."""
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from diag.config import DEFAULT
from diag.generate import generate
from diag.run import diagnose
from diag.score import score

SEEDS = [42, 7, 99, 2026]

if __name__ == "__main__":
    print("## Planted companies (10 planted issues each)\n")
    print("| Seed | Found | Recall | False alarms | Precision | Planted in top 10 |")
    print("|---:|---:|---:|---:|---:|---:|")
    for s in SEEDS:
        t = generate(s)
        r = score(diagnose(t), t["planted"])
        print(f"| {s} | {r['found']}/{r['planted']} | {r['recall']:.0%} | {r['false_alarms']} | {r['precision']:.0%} | {r['planted_in_top']} |")
        for m in r["missed"]:
            print(f"|  | missed {m[0]} {m[1]} | | | | |")
        for m in r["false_alarm_detail"]:
            print(f"|  | false alarm {m[0]} {m[1]} | | | | |")

    print("\n## Clean controls (no planted issues, same noise)\n")
    print("| Seed | Findings | Note |")
    print("|---:|---:|---|")
    for s in SEEDS:
        t = generate(s, planted=False)
        r = score(diagnose(t), t["planted"])
        print(f"| {s} | {r['false_alarms']} | {', '.join(f'{c} {e}' for c, e in r['false_alarm_detail']) or 'none'} |")

    print("\n## Do the dollar assumptions change the ranking? (seed 42, planted issues found in top 10)\n")
    print("| Win rate | Late invoice cost | Hourly cost | Planted in top 10 |")
    print("|---:|---:|---:|---:|")
    t = generate(42)
    for w in (0.15, 0.25, 0.35):
        for c in (0.02, 0.05, 0.10):
            for h in (50.0, 75.0, 120.0):
                a = replace(DEFAULT, win_rate=w, late_invoice_cost=c, hourly_cost=h)
                r = score(diagnose(t, a), t["planted"])
                if (w, c, h) in {(0.15, 0.02, 50.0), (0.25, 0.05, 75.0), (0.35, 0.10, 120.0), (0.15, 0.10, 120.0), (0.35, 0.02, 50.0)}:
                    print(f"| {w} | {c} | {h:.0f} | {r['planted_in_top']} of {r['found']} found |")
