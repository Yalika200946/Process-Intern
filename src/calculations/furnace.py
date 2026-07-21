"""Canonical review-mode CIT and furnace helpers."""

from __future__ import annotations

from src.governance import CalculationResult


def calculate_cit_deficit(measured_c: float, reference_c: float) -> CalculationResult:
    return CalculationResult(
        value=max(0.0, float(reference_c) - float(measured_c)),
        unit="degC",
        basis="max(0, reference CIT - measured CIT)",
        data_kind="CALCULATED",
        confidence="MEDIUM",
        approval_status="CANDIDATE",
        source_columns=("CIT_measured", "CIT_reference"),
        warnings=("Reference must be labelled target or clean-equivalent by the caller.",),
    )


def worst_case_tube_skin(values_c: list[float]) -> CalculationResult:
    finite = [float(value) for value in values_c if value is not None]
    if not finite:
        raise ValueError("At least one tube-skin value is required")
    return CalculationResult(
        value=max(finite), unit="degC", basis="maximum measured furnace-pass tube skin",
        data_kind="CALCULATED", confidence="HIGH", approval_status="CANDIDATE",
        source_columns=tuple(f"tube_skin_pass_{i + 1}" for i in range(len(values_c))),
    )


def calculate_fuel_gas_penalty(
    cit_deficit_c: float, feed_kbd: float, energy_factor_mmbtu_d_kbd_c: float,
    gas_price_thb_mmbtu: float,
) -> CalculationResult:
    value = max(0.0, cit_deficit_c) * feed_kbd * energy_factor_mmbtu_d_kbd_c * gas_price_thb_mmbtu
    return CalculationResult(
        value=value, unit="THB/day",
        basis="CIT deficit x feed KBD x energy factor x gas price",
        data_kind="CALCULATED", confidence="LOW", approval_status="CANDIDATE",
        source_columns=("CIT_deficit", "feed_KBD", "energy_factor", "gas_price"),
        warnings=("Economic scenario estimate; fuel method and dated price require approval.",),
    )

