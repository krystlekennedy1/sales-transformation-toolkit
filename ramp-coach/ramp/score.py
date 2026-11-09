"""Score the coach against planted ground truth."""
from __future__ import annotations

import pandas as pd

from . import config as C


def score(assessments: pd.DataFrame, truth: pd.DataFrame, reps: pd.DataFrame) -> dict:
    m = truth.merge(assessments, on="rep_id").merge(reps[["rep_id", "segment"]], on="rep_id")
    m["troubled"] = m["archetype"] != "healthy"
    m["flagged"] = m["status"] == "at_risk"
    # judged = the coach had enough history to say anything at all
    m["judged"] = m["status"] != "too_early"
    # conversion problems only show once bookings have had time to mature
    m["measurable"] = m.apply(lambda r: r["archetype"] not in ("poor_conversion",) or
                              r["ramp_weeks"] >= C.SEGMENTS[r["segment"]]["cycle_weeks"] + 4, axis=1)
    tp = int((m.troubled & m.flagged).sum())
    fp = int((~m.troubled & m.flagged).sum())
    fn = int((m.troubled & ~m.flagged).sum())
    detectable = m[m.troubled & m.judged & m.measurable]
    caught = detectable[detectable.flagged]
    right = int((caught["diagnosis"] == caught["archetype"]).sum())
    return dict(
        sellers=len(m), troubled=int(m.troubled.sum()), flagged=int(m.flagged.sum()),
        true_pos=tp, false_pos=fp, missed=fn,
        precision=tp / (tp + fp) if tp + fp else 1.0,
        recall=tp / int(m.troubled.sum()),
        detectable=len(detectable), detectable_recall=len(caught) / len(detectable) if len(detectable) else 1.0,
        diagnosis_accuracy=right / len(caught) if len(caught) else 1.0,
        missed_detail=m[m.troubled & ~m.flagged][["rep_id", "archetype", "ramp_weeks", "status"]].to_dict("records"),
        fp_detail=m[~m.troubled & m.flagged][["rep_id", "diagnosis", "ramp_weeks"]].to_dict("records"),
    )
