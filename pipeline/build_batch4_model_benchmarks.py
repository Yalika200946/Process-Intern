"""Consolidate time-based model evidence and apply conservative selection rules."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/tables/mvp_real_data"
OUT = BASE / "full_engineering_program/batch_04"


def selection_status(candidate_rmse, baseline_rmse, *, leakage="", physics_allowed=True) -> tuple[str, str]:
    if pd.isna(candidate_rmse) or pd.isna(baseline_rmse):
        return "INSUFFICIENT_DATA", "MISSING_COMPARABLE_HOLDOUT_METRIC"
    if leakage:
        return "REJECTED", f"TARGET_LEAKAGE:{leakage}"
    if not physics_allowed:
        return "BENCHMARK_ONLY", "PHYSICAL_OR_SEMANTIC_GATE_NOT_OPEN"
    if float(candidate_rmse) < float(baseline_rmse):
        return "SELECTED_PROVISIONAL", "LOWER_CHRONOLOGICAL_HOLDOUT_RMSE"
    return "REJECTED", "DID_NOT_BEAT_SIMPLE_BASELINE"


def reference_baselines(physics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for hx_id, group in physics.groupby("hx_id"):
        frame = group[group.operating_valid.astype(bool) & group.ua_valid.astype(bool)].sort_values("timestamp")
        values = frame.ua_w_m2_k.dropna().to_numpy()
        if len(values) < 60:
            continue
        split = int(len(values) * .8); train, test = values[:split], values[split:]
        median_pred = np.repeat(np.median(train), len(test)); persistence = np.repeat(train[-1], len(test))
        rows.append({"hx_id":hx_id, "median_baseline_rmse":float(np.sqrt(np.mean((test-median_pred)**2))),
                     "persistence_rmse":float(np.sqrt(np.mean((test-persistence)**2))),
                     "train_records":len(train), "test_records":len(test)})
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    physics = pd.read_csv(BASE / "hx_physics_validation.csv", low_memory=False)
    operating = pd.read_csv(BASE / "coverage_completion/operating_adjusted_model_screening.csv")
    baselines = reference_baselines(physics)
    rows = []
    for row in operating.merge(baselines, on="hx_id", how="left").itertuples(index=False):
        baseline = min(row.median_baseline_rmse, row.persistence_rmse)
        status, reason = selection_status(row.holdout_rmse_w_m2_k, baseline, physics_allowed=False)
        rows.append({"task":"REFERENCE_PERFORMANCE", "scope":row.hx_id, "model":"RIDGE_OPERATING_ADJUSTED",
                     "baseline_model":"BEST_OF_MEDIAN_OR_PERSISTENCE", "candidate_rmse":row.holdout_rmse_w_m2_k,
                     "baseline_rmse":baseline, "train_records":row.train_count, "test_records":row.test_count,
                     "validation":"CHRONOLOGICAL_80_20", "selected_status":status, "reason":reason,
                     "physical_rule_checks":"VERIFIED_U_BLOCKED;EMPIRICAL_ONLY"})

    cit = pd.read_csv(BASE / "hx_cit_screening/hx_cit_model_validation.csv")
    for row in cit.itertuples(index=False):
        leakage = row.target_leakage_warning if isinstance(row.target_leakage_warning, str) else ""
        status, reason = selection_status(row.holdout_rmse_c, row.persistence_rmse_c, leakage=leakage)
        rows.append({"task":"HX_CIT_RELATIONSHIP", "scope":row.hx_id, "model":"RIDGE_INTERPRETABLE_SCREENING",
                     "baseline_model":"PERSISTENCE", "candidate_rmse":row.holdout_rmse_c,
                     "baseline_rmse":row.persistence_rmse_c, "train_records":row.train_count,
                     "test_records":row.test_count, "validation":"CHRONOLOGICAL_80_20",
                     "selected_status":status, "reason":reason,
                     "physical_rule_checks":"ASSOCIATION_ONLY;NO_CLEANING_BENEFIT"})

    forecast = pd.read_csv(BASE / "forecast/forecast_summary.csv")
    for row in forecast.itertuples(index=False):
        status, reason = selection_status(row.linear_rmse, row.persistence_rmse)
        rows.append({"task":"CONDITION_TREND", "scope":row.hx_id, "model":"LINEAR_RELATIVE_UA_TREND",
                     "baseline_model":"PERSISTENCE", "candidate_rmse":row.linear_rmse,
                     "baseline_rmse":row.persistence_rmse, "train_records":row.lookback_records-row.holdout_records,
                     "test_records":row.holdout_records, "validation":"CHRONOLOGICAL_HOLDOUT",
                     "selected_status":status, "reason":reason,
                     "physical_rule_checks":"EMPIRICAL_REFERENCE;NOT_CONFIRMED_FOULING"})

    leaderboard = pd.DataFrame(rows)
    leaderboard.to_csv(OUT / "model_leaderboard.csv", index=False)
    method_registry = pd.DataFrame([
        ("REFERENCE_PERFORMANCE","MEDIAN_AND_PERSISTENCE","BENCHMARK_ONLY","executed"),
        ("REFERENCE_PERFORMANCE","RIDGE_OPERATING_ADJUSTED","BENCHMARK_ONLY","verified U and clean state blocked"),
        ("REFERENCE_PERFORMANCE","GAM_OR_ADVANCED_ML","NOT_APPLICABLE","no justified gain before semantic gate"),
        ("HX_CIT_RELATIONSHIP","PERSISTENCE","BENCHMARK_ONLY","executed"),
        ("HX_CIT_RELATIONSHIP","CORRELATION_PARTIAL_AND_RIDGE","SELECTED_PROVISIONAL","association only"),
        ("HX_CIT_RELATIONSHIP","TREE_MODEL","NOT_APPLICABLE","network causal gate not open"),
        ("CONDITION_TREND","PERSISTENCE","BENCHMARK_ONLY","executed"),
        ("CONDITION_TREND","LINEAR_TREND","SELECTED_PROVISIONAL","selected only when holdout improves"),
        ("CONDITION_TREND","SURVIVAL_OR_CYCLE_MODEL","BLOCKED","zero confirmed cycles"),
    ], columns=["task","model","status","reason"])
    method_registry.to_csv(OUT / "model_method_registry.csv", index=False)
    payload = {"batch":4, "status":"PROVISIONAL", "leaderboard_rows":len(leaderboard),
               "selected_provisional":int(leaderboard.selected_status.eq("SELECTED_PROVISIONAL").sum()),
               "rejected":int(leaderboard.selected_status.eq("REJECTED").sum()),
               "benchmark_only":int(leaderboard.selected_status.eq("BENCHMARK_ONLY").sum()),
               "selected_validated":0}
    (OUT / "batch_04_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
