"""Canonical review facade for candidate crude-property correlations."""

from __future__ import annotations

import math

from src.features.crude_properties import cp_rho_crude
from src.governance import CalculationResult


PROPERTY_MODEL = "WATSON_NELSON_LINEAR_CP_AND_THERMAL_EXPANSION_DENSITY"
VALID_TEMPERATURE_RANGE_C = (-20.0, 450.0)
VALID_SG_RANGE = (0.5, 1.2)


def _validate_property_inputs(temperature_c: float, sg_15_6: float) -> tuple[float, float]:
    temperature, sg = float(temperature_c), float(sg_15_6)
    if not math.isfinite(temperature) or not math.isfinite(sg):
        raise ValueError("Crude-property inputs must be finite")
    if not VALID_SG_RANGE[0] <= sg <= VALID_SG_RANGE[1]:
        raise ValueError("Crude SG is outside the supported candidate range")
    if not VALID_TEMPERATURE_RANGE_C[0] <= temperature <= VALID_TEMPERATURE_RANGE_C[1]:
        raise ValueError("Crude temperature is outside the supported candidate range")
    return temperature, sg


def calculate_crude_cp(temperature_c: float, sg_15_6: float) -> CalculationResult:
    temperature, sg = _validate_property_inputs(temperature_c, sg_15_6)
    cp, _ = cp_rho_crude(temperature, sg)
    return CalculationResult(
        value=float(cp), unit="kJ/kg-K", basis="Watson/Nelson-style Cp correlation",
        data_kind="CALCULATED", confidence="LOW", approval_status="CANDIDATE",
        source_columns=("temperature_C", "SG_15_6"),
        warnings=("Correlation and operating range require engineering approval.",),
        quality={"is_valid": True, "property_model": PROPERTY_MODEL,
                 "valid_temperature_range_c": VALID_TEMPERATURE_RANGE_C,
                 "valid_sg_range": VALID_SG_RANGE},
    )


def calculate_crude_density(temperature_c: float, sg_15_6: float) -> CalculationResult:
    temperature, sg = _validate_property_inputs(temperature_c, sg_15_6)
    _, density = cp_rho_crude(temperature, sg)
    return CalculationResult(
        value=float(density), unit="kg/m3", basis="thermal-expansion density correlation",
        data_kind="CALCULATED", confidence="LOW", approval_status="CANDIDATE",
        source_columns=("temperature_C", "SG_15_6"),
        warnings=("Correlation and operating range require engineering approval.",),
        quality={"is_valid": True, "property_model": PROPERTY_MODEL,
                 "valid_temperature_range_c": VALID_TEMPERATURE_RANGE_C,
                 "valid_sg_range": VALID_SG_RANGE},
    )


def calculate_crude_enthalpy_change(t_in_c: float, t_out_c: float, sg_15_6: float) -> CalculationResult:
    """Integrate the canonical linear Cp correlation from inlet to outlet.

    The result is a signed specific-enthalpy change in kJ/kg. For the current
    linear Cp correlation this is numerically identical to Cp at the arithmetic
    mean temperature multiplied by the temperature change.
    """
    t_in, sg = _validate_property_inputs(t_in_c, sg_15_6)
    t_out, _ = _validate_property_inputs(t_out_c, sg)
    root_sg = math.sqrt(sg)
    value = (1.685 * (t_out - t_in) + 0.5 * 0.00339 * (t_out**2 - t_in**2)) / root_sg
    warning = "NEGATIVE_ENTHALPY_CHANGE" if value < 0 else None
    reason = "Outlet temperature is below inlet; signed enthalpy change is preserved." if warning else None
    return CalculationResult(
        value=value, unit="kJ/kg", basis="integral of (1.685 + 0.00339*T)/sqrt(SG) dT",
        data_kind="CALCULATED", confidence="LOW", approval_status="CANDIDATE",
        source_columns=("temperature_in_C", "temperature_out_C", "SG_15_6"),
        warnings=() if reason is None else (reason,),
        quality={"is_valid": warning is None, "warning_code": warning, "reason": reason,
                 "property_model": PROPERTY_MODEL,
                 "valid_temperature_range_c": VALID_TEMPERATURE_RANGE_C,
                 "valid_sg_range": VALID_SG_RANGE},
    )
