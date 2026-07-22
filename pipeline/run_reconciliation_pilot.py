"""Run an evidence-labelled CPHT-2 flow and mix reconciliation pilot."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reconciliation import reconcile_branch_flow_balance, reconcile_common_value

BASE = ROOT / "reports/tables/mvp_real_data"
OUT = BASE / "reconciliation_pilot"


def _flow_rows(frame: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rows = []
    fcfg = cfg["flow_uncertainty"]
    names = ["branch_1fi016", "branch_1fi017", "branch_1fi015", "total_crude"]
    for r in frame.itertuples(index=False):
        values = [r.branch_flow_1, r.branch_flow_2, r.branch_flow_3, r.total_flow]
        finite_positive = all(np.isfinite(v) and v > 0 for v in values)
        if not finite_positive or not bool(r.valid_for_mix_validation):
            for name, value in zip(names, values):
                rows.append({"timestamp": r.timestamp, "variable": name, "measured_value": value,
                             "reconciled_value": np.nan, "inferred_value": np.nan,
                             "reconciliation_adjustment": np.nan, "measurement_uncertainty": np.nan,
                             "normalized_residual": np.nan, "data_kind": "MEASURED",
                             "reconciliation_status": "BLOCKED_BY_DATA", "identifiability_status": "NOT_IDENTIFIABLE",
                             "exclusion_reason": "FLOW_INPUT_OR_OPERATING_STATE_INVALID", "unit": "m3/h"})
            continue
        total_sigma = max(abs(r.total_flow) * fcfg["total_fraction"], fcfg["minimum_m3_h"])
        branch_sigmas = [max(abs(v) * fcfg["branch_fraction"], fcfg["minimum_m3_h"]) for v in values[:3]]
        result = reconcile_branch_flow_balance(r.total_flow, values[:3], total_sigma, branch_sigmas)
        for name, measured, reconciled, adjustment, uncertainty in zip(
                names, result["measured_values"], result["reconciled_values"],
                result["reconciliation_adjustments"], result["measurement_uncertainties"]):
            rows.append({"timestamp": r.timestamp, "variable": name, "measured_value": measured,
                         "reconciled_value": reconciled, "inferred_value": np.nan,
                         "reconciliation_adjustment": adjustment, "measurement_uncertainty": uncertainty,
                         "normalized_residual": result["normalized_residual"], "data_kind": "RECONCILED",
                         "reconciliation_status": result["reconciliation_status"],
                         "identifiability_status": result["identifiability_status"],
                         "exclusion_reason": "", "unit": "m3/h"})
    return pd.DataFrame(rows)


def _mix_rows(frame: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rows = []
    tcfg = cfg["temperature_uncertainty_c"]
    for r in frame.itertuples(index=False):
        values_valid = np.isfinite(r.mix_measured_c) and np.isfinite(r.mix_predicted_c) and bool(r.closure_valid)
        if not values_valid:
            rows.append({"timestamp": r.timestamp, "measured_value": r.mix_measured_c,
                         "calculated_value": r.mix_predicted_c, "reconciled_value": np.nan,
                         "inferred_value": np.nan, "reconciliation_adjustment": np.nan,
                         "measurement_uncertainty": tcfg["measured_mix"], "normalized_residual": np.nan,
                         "data_kind": "MEASURED", "reconciliation_status": "BLOCKED_BY_DATA",
                         "identifiability_status": "NOT_IDENTIFIABLE", "exclusion_reason": r.warning_code,
                         "unit": "degC"})
            continue
        result = reconcile_common_value(r.mix_measured_c, r.mix_predicted_c,
                                        tcfg["measured_mix"], tcfg["calculated_mix"])
        rows.append({"timestamp": r.timestamp, "measured_value": result["measured_value"],
                     "calculated_value": result["calculated_value"], "reconciled_value": result["reconciled_value"],
                     "inferred_value": np.nan, "reconciliation_adjustment": result["reconciled_value"] - result["measured_value"],
                     "measurement_uncertainty": tcfg["measured_mix"], "normalized_residual": result["normalized_residual"],
                     "data_kind": "RECONCILED", "reconciliation_status": "RECONCILED_PROVISIONAL",
                     "identifiability_status": "INFERRED_IDENTIFIABLE", "exclusion_reason": "",
                     "unit": "degC"})
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((ROOT / "config/reconciliation_pilot.json").read_text(encoding="utf-8"))
    flow = pd.read_csv(BASE / "cpht2_mix_validation/cpht2_flow_validation.csv", parse_dates=["timestamp"])
    mix = pd.read_csv(BASE / "cpht2_mix_validation/mix_temperature_closure.csv", parse_dates=["timestamp"])
    flow_out, mix_out = _flow_rows(flow, cfg), _mix_rows(mix, cfg)
    flow_out.to_csv(OUT / "cpht2_flow_reconciliation.csv", index=False)
    mix_out.to_csv(OUT / "cpht2_mix_temperature_reconciliation.csv", index=False)
    flow_valid = flow_out.reconciliation_status.eq("RECONCILED_PROVISIONAL")
    mix_valid = mix_out.reconciliation_status.eq("RECONCILED_PROVISIONAL")
    summary = {
        "stage": "DATA_RECONCILIATION_PILOT", "status": "PROVISIONAL",
        "configuration_scope": "CPHT2_STATIC_MEMBERSHIP_NO_VALVE_CONFIRMATION",
        "flow_reconciled_timestamps": int(flow_out.loc[flow_valid, "timestamp"].nunique()),
        "mix_reconciled_timestamps": int(mix_valid.sum()),
        "flow_median_absolute_normalized_residual": float(flow_out.loc[flow_valid, "normalized_residual"].abs().median()),
        "mix_median_absolute_normalized_residual": float(mix_out.loc[mix_valid, "normalized_residual"].abs().median()),
        "mix_pct_above_warning_threshold": float(100 * mix_out.loc[mix_valid, "normalized_residual"].abs().gt(cfg["normalized_residual_warning_threshold"]).mean()),
        "measured_values_preserved": True, "uncertainty_status": cfg["status"],
        "approval_status": cfg["approval_status"], "full_network_validated": False,
        "downstream_inverse_fouling_allowed": False,
        "blockers": ["CANDIDATE_UNCERTAINTY_WEIGHTS", "STATIC_CONFIGURATION_ONLY", "VERIFIED_AREA_F_UNAVAILABLE", "HOT_SIDE_BALANCE_UNAVAILABLE"]
    }
    (OUT / "reconciliation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    pd.DataFrame([
        {"gate": "CPHT2_BRANCH_FLOW_RECONCILIATION", "status": "PROVISIONAL", "valid_records": summary["flow_reconciled_timestamps"], "blocker": "UNCERTAINTY_AND_CONFIGURATION_NOT_ENGINEER_VALIDATED"},
        {"gate": "CPHT2_MIX_TEMPERATURE_RECONCILIATION", "status": "PROVISIONAL", "valid_records": summary["mix_reconciled_timestamps"], "blocker": "CALCULATED_MIX_INPUTS_INCLUDE_INFERRED_OR_CANDIDATE_PROPERTIES"},
        {"gate": "FULL_NETWORK_RECONCILIATION", "status": "BLOCKED", "valid_records": 0, "blocker": "FULL_TOPOLOGY_AND_TERMINAL_CONFIGURATION_UNRESOLVED"},
        {"gate": "INVERSE_FOULING_STATE", "status": "BLOCKED", "valid_records": 0, "blocker": "VERIFIED_AREA_F_AND_CLEAN_RESISTANCE_BASIS_UNAVAILABLE"},
    ]).to_csv(OUT / "reconciliation_gate_register.csv", index=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
