import numpy as np
import pandas as pd
import pytest

from src.network.validation import (
    classify_configuration_response, classify_mix_node_regime, closure_case_kind, continuity_assessment,
    enthalpy_weighted_mix_temperature, evaluate_network_gates,
    flow_tolerance_sensitivity, segment_event_window,
    pilot_endpoint_counterfactual, screening_threshold_proposal, sequential_temperature_propagation,
)


def test_enthalpy_weighted_mixing_hand_calculation_and_bounds():
    result = enthalpy_weighted_mix_temperature([1, 3], [2, 2], [100, 200])
    assert result["value"] == pytest.approx(175.0)
    assert result["is_valid"]
    assert 100 <= result["value"] <= 200


@pytest.mark.parametrize("flows,code", [([1, 0], "INVALID_BRANCH_FLOW_OR_CP"), ([1, np.nan], "NONFINITE_MIX_INPUT")])
def test_invalid_or_missing_branch_is_excluded(flows, code):
    result = enthalpy_weighted_mix_temperature(flows, [2, 2], [100, 200])
    assert not result["is_valid"]
    assert result["warning_code"] == code


def test_flow_tolerances_are_screening_not_approved_limits():
    result = flow_tolerance_sensitivity([.04, .08, .12, .18])
    assert list(result.within_tolerance_pct) == [25, 50, 75, 100]
    assert set(result.tolerance_status) == {"ANALYTICAL_SCREENING_TOLERANCE"}


def test_inferred_and_measured_closure_cases_are_separate():
    assert closure_case_kind(["MEASURED", "MEASURED"]) == "FULLY_MEASURED"
    assert closure_case_kind(["MEASURED", "INFERRED"]) == "CONTAINS_INFERRED_OR_CALCULATED_INPUT"


def test_mix_node_regime_preserves_inconsistent_measurement():
    assert classify_mix_node_regime(40, 220, 240) == "MIX_NODE_LOW_TEMPERATURE_INCONSISTENT"
    assert classify_mix_node_regime(230, 220, 240) == "MIX_NODE_PHYSICALLY_CONSISTENT"


def test_threshold_proposal_requires_engineering_review():
    result = screening_threshold_proposal([1.0] * 100)
    assert result["status"] == "PROVISIONAL"
    assert result["approval_status"] == "ENGINEERING_REVIEW_REQUIRED"


def test_shared_tag_continuity_is_not_independent():
    result = continuity_assessment("1TI128.pv", "1ti128.PV")
    assert result["continuity_status"] == "SHARED_TAG_NOT_INDEPENDENT"
    assert not result["independent_measurements"]
    assert result["usable_for_network"]


def test_event_window_has_explicit_stabilization_exclusion():
    ts = pd.date_range("2024-01-01", periods=40, tz="UTC")
    segments = segment_event_window(ts, pd.Timestamp("2024-01-20", tz="UTC"), stabilization_days=2)
    assert segments.iloc[19] == "STABILIZATION_EXCLUDED"
    assert segments.iloc[21] == "STABILIZATION_EXCLUDED"
    assert segments.iloc[22] == "POST"


def test_configuration_response_never_claims_confirmation():
    result = classify_configuration_response(pre_count=14, post_count=14, ua_change_fraction=.10,
                                             flow_change_fraction=.01, lmtd_change_fraction=.01,
                                             sensor_valid=True)
    assert result == "CLEANING_RESPONSE_SUPPORTED_BUT_NOT_CONFIRMED"


def test_simple_sequential_temperature_propagation():
    assert sequential_temperature_propagation(50, [lambda x: x + 10, lambda x: x + 5]) == [60, 65]


def test_network_gate_logic_blocks_threshold_required():
    result = evaluate_network_gates({"A": "PASS_PROVISIONAL", "B": "ENGINEERING_THRESHOLD_REQUIRED",
                                     "C": "PASS", "D": "PASS_PROVISIONAL", "E": "PASS"})
    assert not result["counterfactual_cit_can_start"]
    assert result["network_status"] == "BLOCKED_PENDING_STATE_AND_MIX_VALIDATION"


def test_network_gate_logic_allows_explicit_provisional_acceptance():
    result = evaluate_network_gates({"A": "PASS_PROVISIONAL", "B": "PASS_PROVISIONAL"})
    assert result["counterfactual_cit_can_start"]


def test_pilot_endpoint_counterfactual_preserves_local_scope():
    result = pilot_endpoint_counterfactual(900, 90, 100, 10, 100, 2.5)
    assert result["q_recoverable_kw"] == pytest.approx(100)
    assert result["pilot_endpoint_temperature_gain_c"] == pytest.approx(.4)
    assert "not full CIT" in result["basis"]
