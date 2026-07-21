"""Characterization tests for the pre-cleanup CPHT engineering calculations.

These tests intentionally lock the current numerical behavior.  They use only
small, hand-calculated scalar examples and must be updated deliberately if a
later approved phase changes a formula or its validity rules.
"""

import math

import pytest

from src.calculations.fouling import calculate_fouling_indicators
from src.calculations.cit_impact import calculate_single_hx_cit_impact
from src.calculations.heat_duty import calculate_cold_side_heat_duty, calculate_mass_flow
from src.calculations.heat_transfer import calculate_lmtd, calculate_ua
from src.domain.crude_properties import calculate_crude_cp, calculate_crude_density
from src.network.attribution import equivalent_furnace_duty_mw
from src.models.clean_baseline import calculate_clean_baseline


def test_crude_cp_value_and_unit_at_100c_sg_085():
    # (1.685 + 0.00339 * 100) / sqrt(0.85)
    result = calculate_crude_cp(100.0, 0.85)

    assert result.value == pytest.approx(2.1953362331)
    assert result.unit == "kJ/kg-K"


def test_crude_density_value_and_unit_at_100c_sg_085():
    # Current thermal-expansion correlation, evaluated by hand at 100 degC.
    result = calculate_crude_density(100.0, 0.85)

    assert result.value == pytest.approx(787.0225119)
    assert result.unit == "kg/m3"


def test_mass_flow_conversion_is_embedded_in_cold_side_duty():
    # 36 m3/h * 1000 kg/m3 / 3600 = 10 kg/s.  With Cp=1 and dT=1,
    # the numerical duty is therefore 10 kW.
    result = calculate_cold_side_heat_duty(36.0, 1000.0, 1.0, 20.0, 21.0)

    assert result.value == pytest.approx(10.0)
    assert result.unit == "kW"


def test_extracted_mass_flow_conversion_preserves_hand_calculated_case():
    result = calculate_mass_flow(36.0, 1000.0)

    assert result.value == pytest.approx(10.0)
    assert result.unit == "kg/s"
    assert result.quality == {"is_valid": True, "warning_code": None}


def test_zero_mass_flow_is_traceable_without_changing_numerical_behavior():
    result = calculate_mass_flow(0.0, 1000.0)

    assert result.value == 0.0
    assert result.quality["is_valid"] is False
    assert result.quality["warning_code"] == "ZERO_VOLUMETRIC_FLOW"


def test_crude_side_heat_duty_hand_calculation():
    # 100 m3/h * 850 kg/m3 * 2 kJ/kg-K * 10 K / 3600 = 472.222 kW.
    result = calculate_cold_side_heat_duty(100.0, 850.0, 2.0, 100.0, 110.0)

    assert result.value == pytest.approx(472.2222222)
    assert result.quality["delta_t_c"] == pytest.approx(10.0)


def test_lmtd_hand_calculation():
    # (100 - 50) / ln(100 / 50) = 72.134752 degC.
    result = calculate_lmtd(100.0, 50.0)

    assert result.value == pytest.approx(72.13475204)
    assert result.unit == "degC"


def test_lmtd_equal_terminal_differences_uses_limit_value():
    assert calculate_lmtd(40.0, 40.0).value == pytest.approx(40.0)


def test_lmtd_validity_metadata_is_explicit():
    result = calculate_lmtd(100.0, 50.0)

    assert result.quality == {"is_valid": True, "warning_code": None}


def test_ua_hand_calculation_with_correction_factor():
    # UA = 1000 kW / (0.8 * 50 K) = 25 kW/K.
    result = calculate_ua(1000.0, 50.0, correction_factor=0.8)

    assert result.value == pytest.approx(25.0)
    assert result.unit == "kW/K"
    assert result.quality["is_valid"] is True
    assert result.quality["warning_code"] is None


@pytest.mark.parametrize(
    "function,args",
    [
        (calculate_lmtd, (math.nan, 50.0)),
        (calculate_lmtd, (100.0, math.inf)),
        (calculate_ua, (math.nan, 50.0)),
        (calculate_ua, (1000.0, math.inf)),
        (calculate_ua, (1000.0, 50.0, math.nan)),
    ],
)
def test_nonfinite_heat_transfer_inputs_are_rejected(function, args):
    with pytest.raises(ValueError):
        function(*args)


def test_normalized_ua_is_current_performance_ratio():
    result = calculate_fouling_indicators(actual=80.0, clean_equivalent=100.0)

    normalized_ua = result["performance_ratio"]
    assert normalized_ua["value"] == pytest.approx(0.8)
    assert normalized_ua["unit"] == "fraction"


def test_current_fouling_indicator_is_absolute_performance_shortfall():
    result = calculate_fouling_indicators(actual=80.0, clean_equivalent=100.0)

    # The current contract has no explicitly named dimensionless
    # ``fouling_indicator``; its second indicator is an absolute shortfall.
    assert "fouling_indicator" not in result
    assert result["duty_shortfall"]["value"] == pytest.approx(20.0)
    assert result["duty_shortfall"]["unit"] is None


def test_basic_cit_impact_as_equivalent_furnace_duty():
    # 100 m3/h * 850 kg/m3 * 2 kJ/kg-K * 5 K / 3600 / 1000
    # = 0.236111 MW of equivalent furnace duty.
    result_mw = equivalent_furnace_duty_mw(
        cit_recovery_c=5.0,
        charge_m3_h=100.0,
        density_kg_m3=850.0,
        cp_kj_kg_k=2.0,
    )

    assert result_mw == pytest.approx(0.2361111111)


@pytest.mark.parametrize("flow", [-1.0, math.nan, math.inf])
def test_invalid_crude_flow_is_rejected(flow):
    with pytest.raises(ValueError):
        calculate_cold_side_heat_duty(flow, 850.0, 2.0, 100.0, 110.0)


@pytest.mark.parametrize("delta_t1, delta_t2", [(0.0, 50.0), (-1.0, 50.0), (50.0, 0.0)])
def test_invalid_lmtd_terminal_temperatures_are_rejected(delta_t1, delta_t2):
    with pytest.raises(ValueError):
        calculate_lmtd(delta_t1, delta_t2)


def test_nonfinite_heat_duty_temperature_is_rejected():
    with pytest.raises(ValueError):
        calculate_cold_side_heat_duty(100.0, 850.0, 2.0, 100.0, math.nan)


def test_current_negative_cold_side_delta_t_is_warned_not_rejected():
    result = calculate_cold_side_heat_duty(100.0, 850.0, 2.0, 110.0, 100.0)

    assert result.value == pytest.approx(-472.2222222)
    assert result.warnings == ("Cold-side outlet is below inlet; check tags/state.",)
    assert result.quality["is_valid"] is False
    assert result.quality["warning_code"] == "NEGATIVE_COLD_SIDE_DELTA_T"


def test_invalid_ua_denominators_are_rejected():
    with pytest.raises(ValueError):
        calculate_ua(1000.0, 0.0)
    with pytest.raises(ValueError):
        calculate_ua(1000.0, 50.0, correction_factor=0.0)


def test_invalid_clean_baseline_is_rejected():
    with pytest.raises(ValueError):
        calculate_fouling_indicators(actual=80.0, clean_equivalent=0.0)


def test_invalid_negative_cit_inputs_are_rejected():
    with pytest.raises(ValueError):
        equivalent_furnace_duty_mw(-1.0, 100.0, 850.0, 2.0)


def test_clean_window_median_uses_only_explicit_window():
    result = calculate_clean_baseline(
        [90, 100, 110, 120, 130, 1000],
        ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-02-01"],
        "2026-01-01", "2026-01-05", min_valid_records=5,
    )

    assert result["clean_ua"] == pytest.approx(110.0)
    assert result["baseline_method"] == "median"
    assert result["number_of_valid_records"] == 5


def test_clean_window_excludes_invalid_rows():
    result = calculate_clean_baseline(
        [90, 100, math.nan, 110, 120, 130],
        ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"],
        "2026-01-01", "2026-01-06",
        operating_valid=[True, True, True, False, True, True],
        min_valid_records=4,
    )

    assert result["clean_ua"] == pytest.approx(110.0)
    assert result["number_of_valid_records"] == 4
    assert result["quality"]["is_valid"] is True
    assert result["warnings"]


def test_insufficient_clean_observations_are_invalidated():
    result = calculate_clean_baseline(
        [100, 110, 120],
        ["2026-01-01", "2026-01-02", "2026-01-03"],
        "2026-01-01", "2026-01-03", min_valid_records=5,
    )

    assert result["clean_ua"] is None
    assert result["quality"]["warning_code"] == "INSUFFICIENT_CLEAN_DATA"


def test_clean_baseline_has_no_future_data_lookahead():
    timestamps = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-02-01"]
    base = calculate_clean_baseline(
        [90, 100, 110, 120, 130, 140], timestamps,
        "2026-01-01", "2026-01-05", min_valid_records=5,
    )
    future_outlier = calculate_clean_baseline(
        [90, 100, 110, 120, 130, 1_000_000], timestamps,
        "2026-01-01", "2026-01-05", min_valid_records=5,
    )

    assert base["clean_ua"] == future_outlier["clean_ua"] == pytest.approx(110.0)


def test_clean_condition_has_unit_normalized_ua_and_zero_fouling_index():
    result = calculate_fouling_indicators(actual=100.0, clean_equivalent=100.0)

    assert result["ua_normalized"]["value"] == pytest.approx(1.0)
    assert result["fouling_index"]["value"] == pytest.approx(0.0)


def test_degraded_ua_has_positive_fouling_index():
    result = calculate_fouling_indicators(actual=80.0, clean_equivalent=100.0)

    assert result["ua_normalized"]["value"] == pytest.approx(0.8)
    assert result["fouling_index"]["value"] == pytest.approx(0.2)


def test_above_clean_ua_is_warned_without_clipping():
    result = calculate_fouling_indicators(actual=110.0, clean_equivalent=100.0)

    assert result["ua_normalized"]["value"] == pytest.approx(1.1)
    assert result["fouling_index"]["value"] == pytest.approx(-0.1)
    assert result["ua_normalized"]["quality"]["warning_code"] == "ABOVE_CLEAN_BASELINE"


def test_nonfinite_actual_ua_produces_no_numerical_indicator():
    result = calculate_fouling_indicators(actual=math.nan, clean_equivalent=100.0)

    assert result["ua_normalized"]["value"] is None
    assert result["fouling_index"]["value"] is None
    assert result["ua_normalized"]["quality"]["warning_code"] == "NONFINITE_ACTUAL_UA"


def test_invalid_operating_record_produces_no_numerical_indicator():
    result = calculate_fouling_indicators(
        actual=80.0, clean_equivalent=100.0, operating_valid=False,
    )

    assert result["ua_normalized"]["value"] is None
    assert result["fouling_index"]["quality"]["warning_code"] == "INVALID_OPERATING_RECORD"


def test_normalized_ua_and_fouling_index_are_dimensionless():
    result = calculate_fouling_indicators(actual=80.0, clean_equivalent=100.0)

    assert result["ua_normalized"]["unit"] == "fraction"
    assert result["fouling_index"]["unit"] == "fraction"


def test_expected_clean_duty_from_clean_ua_factor_and_lmtd():
    result = calculate_single_hx_cit_impact(
        800.0, 100.0, 2.5, clean_ua_kw_k=20.0,
        lmtd_current_k=50.0, correction_factor=0.9,
    )

    assert result["q_clean_expected"] == pytest.approx(900.0)


def test_positive_recoverable_duty():
    result = calculate_single_hx_cit_impact(
        1000.0, 100.0, 2.5, expected_clean_duty_kw=2000.0,
    )

    assert result["q_deficit_signed"] == pytest.approx(1000.0)
    assert result["q_recoverable"] == pytest.approx(1000.0)


def test_zero_recoverable_duty_is_explicit():
    result = calculate_single_hx_cit_impact(
        1000.0, 100.0, 2.5, expected_clean_duty_kw=1000.0,
    )

    assert result["q_recoverable"] == 0.0
    assert result["cit_gain_equivalent"] == 0.0
    assert result["quality"]["warning_code"] == "NO_RECOVERABLE_DUTY"


def test_actual_duty_above_clean_expectation_preserves_signed_diagnostic():
    result = calculate_single_hx_cit_impact(
        1200.0, 100.0, 2.5, expected_clean_duty_kw=1000.0,
    )

    assert result["q_deficit_signed"] == pytest.approx(-200.0)
    assert result["q_recoverable"] == 0.0
    assert result["cit_gain_equivalent"] == 0.0
    assert result["quality"]["warning_code"] == "ACTUAL_DUTY_ABOVE_CLEAN_EXPECTATION"


def test_equivalent_cit_gain_hand_calculation():
    result = calculate_single_hx_cit_impact(
        1000.0, 100.0, 2.5, expected_clean_duty_kw=2000.0,
    )

    assert result["cit_gain_equivalent"] == pytest.approx(4.0)


@pytest.mark.parametrize("mass_flow", [0.0, -1.0])
def test_nonpositive_crude_mass_flow_is_invalid(mass_flow):
    result = calculate_single_hx_cit_impact(
        1000.0, mass_flow, 2.5, expected_clean_duty_kw=2000.0,
    )

    assert result["cit_gain_equivalent"] is None
    assert result["quality"]["warning_code"] == "INVALID_MASS_FLOW"


def test_nonpositive_crude_cp_is_invalid():
    result = calculate_single_hx_cit_impact(
        1000.0, 100.0, 0.0, expected_clean_duty_kw=2000.0,
    )

    assert result["quality"]["warning_code"] == "INVALID_CRUDE_CP"


def test_invalid_lmtd_is_rejected_without_numerical_impact():
    result = calculate_single_hx_cit_impact(
        1000.0, 100.0, 2.5, clean_ua_kw_k=20.0, lmtd_current_k=0.0,
    )

    assert result["q_recoverable"] is None
    assert result["quality"]["warning_code"] == "INVALID_LMTD"


def test_invalid_clean_ua_is_rejected_without_numerical_impact():
    result = calculate_single_hx_cit_impact(
        1000.0, 100.0, 2.5, clean_ua_kw_k=0.0, lmtd_current_k=50.0,
    )

    assert result["q_recoverable"] is None
    assert result["quality"]["warning_code"] == "INVALID_CLEAN_UA"


def test_invalid_operating_record_has_no_cit_impact():
    result = calculate_single_hx_cit_impact(
        1000.0, 100.0, 2.5, expected_clean_duty_kw=2000.0,
        operating_valid=False,
    )

    assert result["cit_gain_equivalent"] is None
    assert result["quality"]["warning_code"] == "INVALID_OPERATING_RECORD"


def test_cit_impact_units_are_consistent_without_extra_conversion_factor():
    result = calculate_single_hx_cit_impact(
        1000.0, 100.0, 2.5, expected_clean_duty_kw=2000.0,
    )

    assert result["cit_gain_equivalent"] == pytest.approx(1000.0 / (100.0 * 2.5))
    assert result["units"]["q_recoverable"] == "kW"
    assert result["units"]["crude_mass_flow"] == "kg/s"
    assert result["units"]["crude_cp"] == "kJ/kg-K"
    assert result["units"]["cit_gain_equivalent"] == "K"


def test_single_hx_contract_does_not_accept_or_sum_multiple_exchangers():
    with pytest.raises(ValueError, match="single-HX"):
        calculate_single_hx_cit_impact(
            [1000.0, 500.0], 100.0, 2.5, expected_clean_duty_kw=2000.0,
        )


def test_cit_impact_integrates_canonical_mass_baseline_and_fouling_outputs():
    mass_flow = calculate_mass_flow(360.0, 1000.0)
    clean_baseline = calculate_clean_baseline(
        [20, 20, 20, 20, 20],
        ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"],
        "2026-01-01", "2026-01-05", unit="kW/K",
    )
    fouling = calculate_fouling_indicators(actual=16.0, clean_equivalent=20.0)
    impact = calculate_single_hx_cit_impact(
        actual_duty_kw=800.0,
        crude_mass_flow_kg_s=mass_flow,
        crude_cp_kj_kg_k=2.5,
        clean_ua_kw_k=clean_baseline,
        lmtd_current_k=50.0,
    )

    assert fouling["ua_normalized"]["value"] == pytest.approx(0.8)
    assert impact["q_clean_expected"] == pytest.approx(1000.0)
    assert impact["q_recoverable"] == pytest.approx(200.0)
    assert impact["cit_gain_equivalent"] == pytest.approx(0.8)
    assert impact["impact_basis"] == "single_hx_equivalent_crude_temperature_gain"
    assert any("full CPHT network effects" in item for item in impact["assumptions"])
