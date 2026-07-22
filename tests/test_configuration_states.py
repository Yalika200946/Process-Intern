import pandas as pd
import pytest

from src.domain.configuration_states import (
    add_transition_buffer, classify_e101_state, expected_residue_lineup,
    flow_balance, reclassify_signal_event,
)
from pipeline.analyze_configuration_states import build_state_aware_performance


def test_cpht_flow_balance_preserves_signed_residual():
    result = flow_balance(100.0, [30.0, 35.0, 25.0])
    assert result["residual_m3_h"] == pytest.approx(10.0)
    assert result["relative_residual"] == pytest.approx(0.10)
    assert result["balance_status"] == "WITHIN_TOLERANCE"


def test_e101g_substitution_requires_total_operating_and_ef_low():
    result = classify_e101_state(500.0, 0.0)
    assert result["configuration_state"] == "E101G_SUBSTITUTED_INFERRED"
    assert result["active_hx"] == "E101G"
    assert not result["eligible_for_fouling_fit"]


def test_low_total_flow_is_shutdown_not_substitution():
    assert classify_e101_state(10.0, 0.0)["configuration_state"] == "E101_NOT_OPERATING"


def test_grouped_hx_normal_state_remains_group_level():
    result = classify_e101_state(500.0, 100.0)
    assert result["configuration_state"] == "E101EF_NORMAL"
    assert result["active_hx"] == "E101EF"


def test_transition_records_are_excluded_from_fouling_fit():
    frame = pd.DataFrame({"configuration_state": ["E101EF_NORMAL"] * 3 + ["E101G_SUBSTITUTED_INFERRED"] * 3,
                          "configuration_confidence": "MEDIUM", "configuration_evidence": "x",
                          "eligible_for_fouling_fit": True})
    result = add_transition_buffer(frame, records=1)
    assert (result.loc[2:4, "configuration_state"] == "E101_TRANSITION").all()
    assert not result.loc[2:4, "eligible_for_fouling_fit"].any()


def test_residue_sequence_is_state_specific_not_crude_sequence():
    result = expected_residue_lineup("E112AB")
    assert result["expected_lineup"] == "E112AB_CLEANING_E112C_SUBSTITUTE"
    assert result["expected_active_hx"] == ["E113A", "E112C", "E108AB"]


def test_residue_event_not_promoted_without_substitution_history():
    result = reclassify_signal_event("E113A", "BYPASS_OR_SWITCH_CANDIDATE")
    assert result["state_aware_classification"] == "POSSIBLE_CLEANING_REQUIRES_SUBSTITUTION_CONFIRMATION"
    assert result["state_aware_confidence"] == "LOW"


def test_tam_recovery_never_confirms_individual_cleaning():
    result = reclassify_signal_event("E108AB", "TAM_ASSOCIATED_RECOVERY")
    assert result["state_aware_classification"] == "SHUTDOWN_RESTART_RECOVERY"


def test_residue_event_window_is_excluded_but_other_valid_records_remain():
    times = pd.date_range("2024-01-01", periods=10, tz="Asia/Bangkok")
    physics = pd.DataFrame({"timestamp": times, "hx_id": "E113A", "operating_valid": True, "ua_valid": True})
    e101 = pd.DataFrame({"timestamp": times, "configuration_state": "E101EF_NORMAL",
                         "configuration_confidence": "MEDIUM", "eligible_for_fouling_fit": True})
    events = pd.DataFrame({"hx_id": ["E113A"], "event_timestamp": [times[5]],
                           "event_status": ["BYPASS_OR_SWITCH_CANDIDATE"]})
    result = build_state_aware_performance(physics, e101, events, event_window_days=1)
    assert not result.loc[4:6, "eligible_for_state_aware_fouling_fit"].any()
    assert result.loc[[0, 9], "eligible_for_state_aware_fouling_fit"].all()
