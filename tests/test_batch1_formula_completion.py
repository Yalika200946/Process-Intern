import math
import json
from pathlib import Path

import pytest

from src.calculations.heat_duty import calculate_heat_duty_from_enthalpy, reconcile_heat_duties
from src.calculations.heat_transfer import calculate_effectiveness
from src.domain.crude_properties import (
    calculate_crude_cp,
    calculate_crude_density,
    calculate_crude_enthalpy_change,
)
from src.validation.hx_physics import calculate_energy_balance_error


ROOT = Path(__file__).resolve().parents[1]


def test_integrated_linear_cp_matches_midpoint_constant_cp_exactly():
    enthalpy = calculate_crude_enthalpy_change(100.0, 120.0, 0.85)
    midpoint = calculate_crude_cp(110.0, 0.85).value * 20.0
    assert enthalpy.value == pytest.approx(midpoint)
    assert enthalpy.unit == "kJ/kg"
    assert enthalpy.quality["property_model"]


def test_integrated_enthalpy_preserves_negative_sign_and_warning():
    result = calculate_crude_enthalpy_change(120.0, 100.0, 0.85)
    assert result.value < 0
    assert result.quality["warning_code"] == "NEGATIVE_ENTHALPY_CHANGE"


@pytest.mark.parametrize("temperature,sg", [(math.nan, 0.85), (100, 0), (500, 0.85)])
def test_property_model_rejects_nonfinite_or_out_of_range_inputs(temperature, sg):
    with pytest.raises(ValueError):
        calculate_crude_density(temperature, sg)


def test_enthalpy_duty_unit_identity_kj_per_second_is_kw():
    result = calculate_heat_duty_from_enthalpy(10.0, 50.0, stream_label="cold")
    assert result.value == pytest.approx(500.0)
    assert result.unit == "kW"
    assert result.quality["stream_label"] == "cold"


def test_reconciled_duty_uses_inverse_variance_weights():
    result = reconcile_heat_duties(100.0, 120.0, 10.0, 20.0)
    assert result.value == pytest.approx(104.0)
    assert result.unit == "kW"


def test_reconciled_duty_requires_explicit_positive_uncertainty():
    with pytest.raises(ValueError):
        reconcile_heat_duties(100.0, 120.0, 0.0, 20.0)


def test_effectiveness_hand_calculation_and_bounds():
    result = calculate_effectiveness(1000.0, 20.0, 30.0, 150.0, 50.0)
    assert result.value == pytest.approx(0.5)
    assert result.quality["q_max_kw"] == pytest.approx(2000.0)
    assert result.quality["is_valid"] is True


def test_effectiveness_above_one_is_preserved_and_invalidated():
    result = calculate_effectiveness(2500.0, 20.0, 30.0, 150.0, 50.0)
    assert result.value == pytest.approx(1.25)
    assert result.quality["warning_code"] == "EFFECTIVENESS_OUT_OF_BOUNDS"


def test_energy_closure_hand_calculation_and_unit():
    result = calculate_energy_balance_error(1100.0, 1000.0)
    assert result.value == pytest.approx(100.0 / 1100.0)
    assert result.unit == "fraction"
    assert result.quality["signed_error_kw"] == pytest.approx(100.0)


def test_zero_duty_closure_is_traceable_without_division():
    result = calculate_energy_balance_error(0.0, 0.0)
    assert result.value is None
    assert result.quality["is_valid"] is False
    assert result.quality["warning_code"] == "ZERO_DUTY_REFERENCE"


def test_batch1_registries_preserve_ua_u_and_property_semantics():
    units = json.loads((ROOT / "config/unit_registry.json").read_text(encoding="utf-8"))["records"]
    by_quantity = {row["quantity"]: row for row in units}
    assert by_quantity["conductance_UA"]["canonical_unit"] == "kW/K"
    assert by_quantity["heat_transfer_coefficient_U"]["canonical_unit"] == "W/m2-K"
    assert by_quantity["heat_transfer_coefficient_U"]["status"] == "BLOCKED"

    areas = json.loads((ROOT / "config/area_and_f_registry.json").read_text(encoding="utf-8"))["records"]
    assert len(areas) == 17
    assert not any(row["area_status"].startswith("VERIFIED") for row in areas)
    assert all(row["F_status"] != "VERIFIED" for row in areas)

    properties = json.loads((ROOT / "config/property_model_registry.json").read_text(encoding="utf-8"))["records"]
    assert properties[0]["status"] == "PROVISIONAL"
    assert properties[0]["uncertainty"] == "UNQUANTIFIED"
