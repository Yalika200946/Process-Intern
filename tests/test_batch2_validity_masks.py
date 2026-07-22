import pandas as pd

from pipeline.build_batch2_validity_masks import build_masks


def test_masks_are_conservative_and_preserve_exclusion_reasons():
    state = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=2, tz="Asia/Bangkok"),
        "hx_id": ["E104", "E104"], "data_available": [True, True],
        "operating_valid": [True, False], "configuration_confidence": ["MEDIUM", "LOW"],
        "configuration_state": ["STATIC_MEMBERSHIP_ONLY", "RESIDUE_EVENT_UNCERTAIN"],
        "mass_flow_valid": [True, True], "q_cold_valid": [True, True],
        "lmtd_valid": [True, True], "ua_valid": [True, True], "data_kind": ["MEASURED", "MEASURED"],
        "quality_warning_code": ["", "TRANSIENT"], "state_aware_exclusion_reason": ["", "CONFIGURATION_UNCERTAIN"],
    })
    mix = pd.DataFrame({"timestamp": state.timestamp, "closure_valid": [True, False]})
    furnace = pd.DataFrame({"timestamp": state.timestamp, "f101_duty_physics_kw": [1000.0, None]})
    result = build_masks(state, mix, furnace)
    assert result.loc[0, "baseline_fit_valid"]
    assert result.loc[0, "network_valid"]
    assert result.loc[0, "furnace_model_valid"]
    assert not result.loc[1, "configuration_valid"]
    assert not result.loc[1, "baseline_fit_valid"]
    assert "CONFIGURATION_VALID" in result.loc[1, "mask_exclusion_reasons"]
    assert result.raw_values_preserved.all()


def test_no_mask_can_promote_an_invalid_hx_calculation():
    state = pd.DataFrame({
        "timestamp": [pd.Timestamp("2026-01-01", tz="Asia/Bangkok")], "hx_id": ["E104"],
        "data_available": [True], "operating_valid": [True], "configuration_confidence": ["MEDIUM"],
        "configuration_state": ["STATIC_MEMBERSHIP_ONLY"], "mass_flow_valid": [True],
        "q_cold_valid": [True], "lmtd_valid": [True], "ua_valid": [False], "data_kind": ["MEASURED"],
        "quality_warning_code": ["INVALID_UA"], "state_aware_exclusion_reason": ["ORIGINAL_UA_INVALID"],
    })
    mix = pd.DataFrame({"timestamp": state.timestamp, "closure_valid": [True]})
    furnace = pd.DataFrame({"timestamp": state.timestamp, "f101_duty_physics_kw": [1000.0]})
    result = build_masks(state, mix, furnace).iloc[0]
    assert not result.hx_calculation_valid
    assert not result.baseline_fit_valid
    assert not result.trend_fit_valid
    assert not result.network_valid
    assert not result.furnace_model_valid
