"""Small, auditable helpers for CPHT split/mix and pilot-network validation."""
from __future__ import annotations

import numpy as np
import pandas as pd


def enthalpy_weighted_mix_temperature(mass_flows, cp_values, temperatures) -> dict:
    arrays = [np.asarray(values, dtype=float) for values in (mass_flows, cp_values, temperatures)]
    if not all(array.size and len(array) == len(arrays[0]) for array in arrays):
        return {"value": None, "is_valid": False, "warning_code": "MISSING_BRANCH_INPUT"}
    m, cp, temp = arrays
    if not (np.isfinite(m).all() and np.isfinite(cp).all() and np.isfinite(temp).all()):
        return {"value": None, "is_valid": False, "warning_code": "NONFINITE_MIX_INPUT"}
    if (m <= 0).any() or (cp <= 0).any():
        return {"value": None, "is_valid": False, "warning_code": "INVALID_BRANCH_FLOW_OR_CP"}
    weights = m * cp
    value = float(np.sum(weights * temp) / np.sum(weights))
    lower, upper = float(temp.min()), float(temp.max())
    valid = lower - 1e-9 <= value <= upper + 1e-9
    return {"value": value if valid else None, "is_valid": valid,
            "warning_code": "" if valid else "MIX_OUTSIDE_PHYSICAL_BOUNDS",
            "inlet_min_c": lower, "inlet_max_c": upper,
            "basis": "sum(m_dot*Cp*T)/sum(m_dot*Cp)", "unit": "degC"}


def flow_tolerance_sensitivity(relative_residual, tolerances=(0.05, 0.10, 0.15, 0.20)) -> pd.DataFrame:
    values = pd.to_numeric(pd.Series(relative_residual), errors="coerce").dropna().abs()
    return pd.DataFrame([{"tolerance_fraction": tolerance,
                          "tolerance_status": "ANALYTICAL_SCREENING_TOLERANCE",
                          "valid_records": len(values),
                          "within_tolerance_pct": 100 * float(values.le(tolerance).mean()) if len(values) else 0.0}
                         for tolerance in tolerances])


def closure_case_kind(data_kinds) -> str:
    kinds = {str(value).upper() for value in data_kinds}
    if "UNAVAILABLE" in kinds:
        return "UNAVAILABLE_INPUT"
    if kinds <= {"MEASURED"}:
        return "FULLY_MEASURED"
    return "CONTAINS_INFERRED_OR_CALCULATED_INPUT"


def continuity_assessment(upstream_tag: str | None, downstream_tag: str | None,
                          upstream_values=None, downstream_values=None) -> dict:
    if not upstream_tag or not downstream_tag:
        return {"independent_measurements": False, "continuity_status": "BLOCKED",
                "usable_for_network": False, "likely_cause": "MISSING_TAG_MAPPING"}
    if upstream_tag.casefold() == downstream_tag.casefold():
        return {"independent_measurements": False, "median_difference_C": 0.0, "MAE_C": 0.0,
                "detected_lag": 0, "continuity_status": "SHARED_TAG_NOT_INDEPENDENT",
                "usable_for_network": True, "likely_cause": "SAME_SENSOR_USED_FOR_ADJACENT_NODES"}
    if upstream_values is None or downstream_values is None:
        return {"independent_measurements": True, "continuity_status": "INSUFFICIENT_DATA",
                "usable_for_network": False, "likely_cause": "VALUES_UNAVAILABLE"}
    left, right = pd.to_numeric(pd.Series(upstream_values), errors="coerce"), pd.to_numeric(pd.Series(downstream_values), errors="coerce")
    valid = left.notna() & right.notna(); difference = left[valid] - right[valid]
    if len(difference) < 7:
        return {"independent_measurements": True, "continuity_status": "INSUFFICIENT_DATA",
                "usable_for_network": False, "likely_cause": "TOO_FEW_VALID_PAIRS"}
    mae = float(difference.abs().mean())
    return {"independent_measurements": True, "median_difference_C": float(difference.median()),
            "MAE_C": mae, "detected_lag": 0,
            "continuity_status": "CONTINUITY_PROVISIONAL" if mae <= 3 else "SENSOR_BIAS_SUSPECT",
            "usable_for_network": mae <= 3, "likely_cause": "MEASURED_PAIR_SCREENING"}


def segment_event_window(timestamps, event_timestamp, *, pre_days=14, stabilization_days=3, post_days=14):
    ts = pd.to_datetime(pd.Series(timestamps), utc=True)
    event = pd.Timestamp(event_timestamp)
    event = event.tz_localize("UTC") if event.tzinfo is None else event.tz_convert("UTC")
    result = pd.Series("OUTSIDE", index=ts.index, dtype="object")
    result.loc[ts.between(event - pd.Timedelta(days=pre_days), event - pd.Timedelta(days=1))] = "PRE"
    result.loc[ts.between(event, event + pd.Timedelta(days=stabilization_days))] = "STABILIZATION_EXCLUDED"
    result.loc[ts.between(event + pd.Timedelta(days=stabilization_days + 1),
                          event + pd.Timedelta(days=stabilization_days + post_days))] = "POST"
    return result


def classify_configuration_response(*, pre_count: int, post_count: int, ua_change_fraction,
                                    flow_change_fraction, lmtd_change_fraction,
                                    sensor_valid: bool, original_rejected: bool = False) -> str:
    if pre_count < 7 or post_count < 7:
        return "INSUFFICIENT_EVIDENCE"
    if not sensor_valid:
        return "SENSOR_EFFECT_LIKELY"
    if abs(flow_change_fraction) > 0.10 or abs(lmtd_change_fraction) > 0.10:
        return "PROCESS_CHANGE_LIKELY"
    if original_rejected:
        return "RESPONSE_INCONSISTENT"
    if ua_change_fraction >= 0.05:
        return "CLEANING_RESPONSE_SUPPORTED_BUT_NOT_CONFIRMED"
    if abs(ua_change_fraction) < 0.05:
        return "CONFIGURATION_SWITCH_LIKELY"
    return "RESPONSE_INCONSISTENT"


def evaluate_network_gates(gates: dict[str, str]) -> dict:
    allowed = {"PASS", "PASS_PROVISIONAL"}
    ready = all(value in allowed for value in gates.values())
    return {"network_status": "PILOT_NETWORK_READY_FOR_COUNTERFACTUAL" if ready
            else "BLOCKED_PENDING_STATE_AND_MIX_VALIDATION",
            "counterfactual_cit_can_start": ready,
            "failed_or_blocked_gates": [name for name, value in gates.items() if value not in allowed]}


def sequential_temperature_propagation(inlet, stage_predictors):
    value = float(inlet); outputs = []
    for predictor in stage_predictors:
        value = float(predictor(value)); outputs.append(value)
    return outputs
