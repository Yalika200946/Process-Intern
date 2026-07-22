"""Execute empirical condition and multi-method event screening without confirmation claims."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.events.change_detection import cusum_recovery_screen, ewma_innovation_screen, robust_step_screen

BASE = ROOT / "reports/tables/mvp_real_data"
OUT = BASE / "full_engineering_program/batch_03"


def _spaced_candidates(frame: pd.DataFrame, days: int = 14) -> pd.DataFrame:
    chosen = []
    for _, group in frame.groupby(["hx_id", "method"]):
        last = None
        for row in group.sort_values("timestamp").itertuples(index=False):
            if last is not None and row.timestamp - last < pd.Timedelta(days=days):
                continue
            chosen.append(row); last = row.timestamp
    return pd.DataFrame(chosen, columns=frame.columns) if chosen else frame.iloc[0:0].copy()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    relative = pd.read_csv(BASE / "empirical_relative_performance/relative_performance_timeseries.csv")
    relative["timestamp"] = pd.to_datetime(relative.timestamp, utc=True)
    masks = pd.read_csv(BASE / "full_engineering_program/batch_02/canonical_validity_masks.csv")
    masks["timestamp"] = pd.to_datetime(masks.timestamp, utc=True)
    mask_cols = ["timestamp", "hx_id", "trend_fit_valid", "configuration_valid", "mask_exclusion_reasons"]
    data = relative.merge(masks[mask_cols], on=["timestamp", "hx_id"], how="left")
    data = data[data.trend_fit_valid.fillna(False)].sort_values(["hx_id", "timestamp"])

    detector_rows = []
    for hx_id, group in data.groupby("hx_id"):
        values = group.relative_ua_empirical.reset_index(drop=True)
        methods = [robust_step_screen(values), cusum_recovery_screen(values), ewma_innovation_screen(values)]
        for result in methods:
            result = result.copy(); result["timestamp"] = group.timestamp.to_numpy(); result["hx_id"] = hx_id
            detector_rows.append(result[result.candidate].copy())
    detections = pd.concat(detector_rows, ignore_index=True) if detector_rows else pd.DataFrame()
    detections = _spaced_candidates(detections) if len(detections) else detections
    detections["cleaning_event_confirmed"] = False
    detections["clean_condition_confirmed"] = False
    detections["status"] = "EXPLORATORY"
    detections["evidence_limit"] = "SIGNAL_ONLY_NO_MAINTENANCE_OR_VALVE_CONFIRMATION"
    detections.to_csv(OUT / "multi_method_event_detections.csv", index=False)

    if len(detections):
        consensus = detections.assign(day=detections.timestamp.dt.floor("14D")).groupby(["hx_id", "day"]).agg(
            method_count=("method", "nunique"), methods=("method", lambda x: "|".join(sorted(set(x)))),
            maximum_score=("score", "max"), event_date=("timestamp", "min")
        ).reset_index(drop=False)
        consensus["classification"] = consensus.method_count.map(
            lambda count: "CLEANING_RESPONSE_SUPPORTED_BUT_NOT_CONFIRMED" if count >= 2 else "POSSIBLE_CLEANING")
        consensus["cleaning_event_confirmed"] = False
        consensus["usable_as_confirmed_cycle_boundary"] = False
        consensus["status"] = "EXPLORATORY"
    else:
        consensus = pd.DataFrame(columns=["hx_id", "day", "method_count", "methods", "maximum_score", "event_date",
                                               "classification", "cleaning_event_confirmed",
                                               "usable_as_confirmed_cycle_boundary", "status"])
    consensus.to_csv(OUT / "event_consensus_registry.csv", index=False)

    method_summary = detections.groupby(["hx_id", "method"]).size().rename("candidate_count").reset_index() if len(detections) else pd.DataFrame(columns=["hx_id", "method", "candidate_count"])
    method_summary["selected_status"] = "BENCHMARK_ONLY"
    method_summary["confirmation_allowed"] = False
    method_summary.to_csv(OUT / "event_method_comparison.csv", index=False)

    pd.DataFrame([{"cycle_model_status":"BLOCKED", "confirmed_cycles":0,
                   "reason":"No confirmed cleaning events; degradation curves and survival models are not eligible."}]).to_csv(OUT / "cycle_analysis_blocker.csv", index=False)
    payload = {"batch": 3, "status": "EXPLORATORY", "eligible_hx": int(data.hx_id.nunique()),
               "detector_candidates": int(len(detections)), "consensus_windows": int(len(consensus)),
               "confirmed_cleaning_events": 0, "confirmed_cycles": 0,
               "confirmed_fouling_fields_generated": False}
    (OUT / "batch_03_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
