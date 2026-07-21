"""Characterization tests for the pre-cleanup CPHT engineering calculations.

These tests intentionally lock the current numerical behavior.  They use only
small, hand-calculated scalar examples and must be updated deliberately if a
later approved phase changes a formula or its validity rules.
"""

import math

import pytest

from src.calculations.fouling import calculate_fouling_indicators
from src.calculations.heat_duty import calculate_cold_side_heat_duty, calculate_mass_flow
from src.calculations.heat_transfer import calculate_lmtd, calculate_ua
from src.domain.crude_properties import calculate_crude_cp, calculate_crude_density
from src.network.attribution import equivalent_furnace_duty_mw


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


def test_ua_hand_calculation_with_correction_factor():
    # UA = 1000 kW / (0.8 * 50 K) = 25 kW/K.
    result = calculate_ua(1000.0, 50.0, correction_factor=0.8)

    assert result.value == pytest.approx(25.0)
    assert result.unit == "kW/K"


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
