"""Build conservative, traceable validity masks from existing real-data evidence."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BASE = ROOT / "reports/tables/mvp_real_data"
OUT = BASE / "full_engineering_program/batch_02"


def build_masks(state_aware: pd.DataFrame, mix: pd.DataFrame, furnace: pd.DataFrame) -> pd.DataFrame:
    frame = state_aware.copy()
    frame["timestamp"] = pd.to_datetime(frame.timestamp, utc=True)
    frame["data_valid"] = frame.data_available.astype(bool)
    frame["steady_state_valid"] = frame.operating_valid.astype(bool)
    frame["configuration_valid"] = (
        ~frame.configuration_confidence.fillna("LOW").eq("LOW")
        & ~frame.configuration_state.fillna("UNKNOWN").isin(["SUBSTITUTED", "RESIDUE_EVENT_UNCERTAIN"])
    )
    frame["hx_calculation_valid"] = frame[["mass_flow_valid", "q_cold_valid", "lmtd_valid", "ua_valid"]].fillna(False).all(axis=1)
    frame["baseline_fit_valid"] = (
        frame.steady_state_valid & frame.configuration_valid & frame.hx_calculation_valid
        & ~frame.data_kind.fillna("UNAVAILABLE").eq("UNAVAILABLE")
    )
    frame["trend_fit_valid"] = frame.baseline_fit_valid

    eligible_mix = mix.copy()
    eligible_mix["timestamp"] = pd.to_datetime(eligible_mix.timestamp, utc=True)
    eligible_timestamps = set(eligible_mix.loc[eligible_mix.closure_valid.astype(bool), "timestamp"])
    network_hx = {"E103AB", "E104", "E105AB", "E106AB", "E107AB", "E108AB", "E109AB", "E110ABC", "E111", "E112AB", "E113A"}
    frame["network_valid"] = frame.hx_id.isin(network_hx) & frame.timestamp.isin(eligible_timestamps) & frame.hx_calculation_valid & frame.configuration_valid

    furnace = furnace.copy()
    furnace["timestamp"] = pd.to_datetime(furnace.timestamp, utc=True)
    furnace_timestamps = set(furnace.loc[furnace.f101_duty_physics_kw.notna(), "timestamp"])
    frame["furnace_model_valid"] = frame.timestamp.isin(furnace_timestamps) & frame.hx_calculation_valid

    mask_columns = ["data_valid", "steady_state_valid", "configuration_valid", "hx_calculation_valid",
                    "baseline_fit_valid", "trend_fit_valid", "network_valid", "furnace_model_valid"]
    reasons = []
    for row in frame.itertuples(index=False):
        failed = [name.upper() for name in mask_columns if not getattr(row, name)]
        reasons.append("|".join(failed))
    frame["mask_exclusion_reasons"] = reasons
    frame["raw_values_preserved"] = True
    frame["mask_status"] = "PROVISIONAL"  # configuration/network evidence remains incomplete
    return frame[["timestamp", "hx_id", *mask_columns, "mask_exclusion_reasons",
                  "quality_warning_code", "state_aware_exclusion_reason",
                  "configuration_state", "configuration_confidence", "raw_values_preserved", "mask_status"]]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    state = pd.read_csv(BASE / "configuration_states/state_aware_hx_performance.csv", low_memory=False)
    mix = pd.read_csv(BASE / "cpht2_mix_validation/mix_temperature_closure.csv", low_memory=False)
    furnace = pd.read_csv(BASE / "f101_consequence/f101_physics_timeseries.csv", low_memory=False)
    masks = build_masks(state, mix, furnace)
    masks.to_csv(OUT / "canonical_validity_masks.csv", index=False)
    columns = [name for name in masks if name.endswith("_valid")]
    summary = masks.groupby("hx_id")[columns].mean().mul(100).reset_index()
    summary.to_csv(OUT / "validity_mask_coverage_by_hx.csv", index=False)
    warning = masks.groupby(["hx_id", "mask_exclusion_reasons"], dropna=False).size().rename("records").reset_index()
    warning.to_csv(OUT / "mask_exclusion_summary.csv", index=False)
    checks = pd.DataFrame([
        ("missing_values", "VALIDATED", "record-level required-input availability"),
        ("duplicate_timestamps", "VALIDATED", "source timestamp audit"),
        ("irregular_sampling_and_gaps", "VALIDATED", "interval and long-gap audit"),
        ("flatline", "VALIDATED", "exact-run sensor screening"),
        ("range_and_temperature_physics", "VALIDATED", "configured range and terminal-difference rules"),
        ("rate_of_change", "PROVISIONAL", "steady flow and temperature change rules"),
        ("sensor_discontinuity", "PARTIAL", "rate/change evidence only; no instrument-specific calibration history"),
        ("time_alignment", "PROVISIONAL", "daily source matrix aligned by timestamp; lag screen remains analytical"),
        ("configuration_switching", "PROVISIONAL", "signal-inferred states without valve history"),
        ("maintenance", "BLOCKED", "no complete work-order history"),
    ], columns=["check", "status", "basis_or_blocker"])
    checks.to_csv(OUT / "data_quality_check_registry.csv", index=False)
    payload = {"batch": 2, "status": "PROVISIONAL", "records": len(masks),
               "hx": int(masks.hx_id.nunique()), "raw_values_preserved": True,
               "configuration_validated": False, "network_validated": False}
    (OUT / "batch_02_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
