"""Canonical review facade for candidate crude-property correlations."""

from __future__ import annotations

from src.features.crude_properties import cp_rho_crude
from src.governance import CalculationResult


def calculate_crude_cp(temperature_c: float, sg_15_6: float) -> CalculationResult:
    cp, _ = cp_rho_crude(float(temperature_c), float(sg_15_6))
    return CalculationResult(
        value=float(cp), unit="kJ/kg-K", basis="Watson/Nelson-style Cp correlation",
        data_kind="CALCULATED", confidence="LOW", approval_status="CANDIDATE",
        source_columns=("temperature_C", "SG_15_6"),
        warnings=("Correlation and operating range require engineering approval.",),
    )


def calculate_crude_density(temperature_c: float, sg_15_6: float) -> CalculationResult:
    _, density = cp_rho_crude(float(temperature_c), float(sg_15_6))
    return CalculationResult(
        value=float(density), unit="kg/m3", basis="thermal-expansion density correlation",
        data_kind="CALCULATED", confidence="LOW", approval_status="CANDIDATE",
        source_columns=("temperature_C", "SG_15_6"),
        warnings=("Correlation and operating range require engineering approval.",),
    )

