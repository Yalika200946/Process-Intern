"""Conservative CPHT configuration-state and flow-balance helpers."""
from __future__ import annotations

import numpy as np
import pandas as pd


def flow_balance(total, components, *, tolerance_fraction: float = 0.15) -> dict:
    values = [total, *components]
    if not all(np.isfinite(value) for value in values):
        return {"component_sum_m3_h": None, "residual_m3_h": None,
                "relative_residual": None, "balance_status": "NONFINITE_FLOW"}
    component_sum = float(sum(components))
    residual = float(total - component_sum)
    relative = residual / float(total) if total > 0 else None
    status = "WITHIN_TOLERANCE" if total > 0 and abs(relative) <= tolerance_fraction else "OUTSIDE_TOLERANCE"
    return {"component_sum_m3_h": component_sum, "residual_m3_h": residual,
            "relative_residual": relative, "balance_status": status}


def classify_e101_state(total_flow, ef_flow, *, total_min: float = 50.0,
                         branch_min: float = 15.0) -> dict:
    if not np.isfinite(total_flow):
        return _state("E101_UNKNOWN_CONFIGURATION", "LOW", "TOTAL_CRUDE_NONFINITE", False)
    if total_flow < total_min:
        return _state("E101_NOT_OPERATING", "HIGH", "TOTAL_CRUDE_BELOW_OPERATING_THRESHOLD", False)
    if not np.isfinite(ef_flow):
        return _state("E101_UNKNOWN_CONFIGURATION", "LOW", "E101EF_FLOW_NONFINITE", False)
    if ef_flow < branch_min:
        return _state("E101G_SUBSTITUTED_INFERRED", "MEDIUM",
                      "TOTAL_CRUDE_OPERATING_AND_E101EF_FLOW_LOW", False,
                      active_hx="E101G", substituted_hx="E101EF")
    return _state("E101EF_NORMAL", "MEDIUM", "TOTAL_CRUDE_AND_E101EF_FLOW_OPERATING", True,
                  active_hx="E101EF")


def _state(state, confidence, evidence, eligible, active_hx=None, substituted_hx=None):
    return {"configuration_state": state, "configuration_confidence": confidence,
            "configuration_evidence": evidence, "eligible_for_fouling_fit": eligible,
            "active_hx": active_hx, "substituted_hx": substituted_hx}


def add_transition_buffer(frame: pd.DataFrame, records: int = 2) -> pd.DataFrame:
    result = frame.copy()
    changed = result.configuration_state.ne(result.configuration_state.shift())
    positions = np.flatnonzero(changed.to_numpy())
    for position in positions:
        if position == 0:
            continue
        left, right = max(0, position - records), min(len(result), position + records + 1)
        result.loc[result.index[left:right], "configuration_state"] = "E101_TRANSITION"
        result.loc[result.index[left:right], "configuration_confidence"] = "MEDIUM"
        result.loc[result.index[left:right], "configuration_evidence"] = "STATE_CHANGE_BUFFER"
        result.loc[result.index[left:right], "eligible_for_fouling_fit"] = False
    return result


def expected_residue_lineup(cleaning_hx: str) -> dict:
    cases = {
        "E113A": ("E113A_CLEANING_E112C_SUBSTITUTE", ["E112C", "E112AB", "E108AB"]),
        "E112C": ("E112C_CLEANING", ["E113A", "E112AB", "E108AB"]),
        "E112AB": ("E112AB_CLEANING_E112C_SUBSTITUTE", ["E113A", "E112C", "E108AB"]),
    }
    if cleaning_hx not in cases:
        return {"expected_lineup": "NO_CONFIRMED_SUBSTITUTION_RULE", "expected_active_hx": [],
                "substitution_evidence_required": False}
    state, active = cases[cleaning_hx]
    return {"expected_lineup": state, "expected_active_hx": active,
            "substitution_evidence_required": True}


def reclassify_signal_event(hx_id: str, event_status: str) -> dict:
    if event_status in {"REJECTED_SIGNAL_EVENT", "NOT_CLEANING_ELIGIBLE_MID_RUN"}:
        return {"state_aware_classification": "REJECTED_SIGNAL", "state_aware_confidence": "HIGH",
                "state_aware_warning_code": "ORIGINAL_SCREENING_REJECTED"}
    if event_status == "TAM_ASSOCIATED_RECOVERY":
        return {"state_aware_classification": "SHUTDOWN_RESTART_RECOVERY",
                "state_aware_confidence": "MEDIUM",
                "state_aware_warning_code": "INDIVIDUAL_CLEANING_NOT_CONFIRMED"}
    if hx_id in {"E113A", "E112C", "E112AB"}:
        return {"state_aware_classification": "POSSIBLE_CLEANING_REQUIRES_SUBSTITUTION_CONFIRMATION",
                "state_aware_confidence": "LOW",
                "state_aware_warning_code": "NO_VALVE_OR_SUBSTITUTE_STATE_HISTORY"}
    if hx_id == "E108AB":
        return {"state_aware_classification": "POSSIBLE_CLEANING_REQUIRES_ROUTING_CONFIRMATION",
                "state_aware_confidence": "LOW",
                "state_aware_warning_code": "E108AB_CLEANING_ROUTING_NOT_CONFIRMED"}
    if hx_id == "E101EF":
        return {"state_aware_classification": "CONFIGURATION_SWITCH_CANDIDATE",
                "state_aware_confidence": "MEDIUM",
                "state_aware_warning_code": "CHECK_E101G_SUBSTITUTION_TIMELINE"}
    return {"state_aware_classification": "POSSIBLE_CLEANING",
            "state_aware_confidence": "LOW", "state_aware_warning_code": "NO_MAINTENANCE_EVIDENCE"}
