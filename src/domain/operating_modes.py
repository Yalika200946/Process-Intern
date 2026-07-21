"""Canonical operating-mode helpers; notebooks remain the classification orchestrator."""

from src.calculations.mass_balance import infer_e101g_flow


def infer_e101g_state_and_flow(total_charge, e101ab, e101cd, e101ef, active_threshold=30.0):
    result = infer_e101g_flow(total_charge, e101ab, e101cd, e101ef)
    return {
        "flow": result.to_dict(),
        "state": "SUBSTITUTE_ACTIVE" if result.value >= active_threshold else "OFF",
        "measurement_type": "INFERRED",
        "approval_status": "CANDIDATE",
    }

