"""Canonical cold-side heat-duty calculations with explicit provenance."""

from __future__ import annotations

import math

from src.governance import CalculationResult


def calculate_cold_side_heat_duty(
    volumetric_flow_m3_h: float,
    density_kg_m3: float,
    cp_kj_kg_k: float,
    cold_in_c: float,
    cold_out_c: float,
) -> CalculationResult:
    values = (volumetric_flow_m3_h, density_kg_m3, cp_kj_kg_k, cold_in_c, cold_out_c)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("Heat-duty inputs must be finite")
    if volumetric_flow_m3_h < 0 or density_kg_m3 <= 0 or cp_kj_kg_k <= 0:
        raise ValueError("Flow must be non-negative; density and Cp must be positive")
    delta_t = cold_out_c - cold_in_c
    duty_kw = volumetric_flow_m3_h * density_kg_m3 * cp_kj_kg_k * delta_t / 3600.0
    warnings = () if delta_t >= 0 else ("Cold-side outlet is below inlet; check tags/state.",)
    return CalculationResult(
        value=duty_kw,
        unit="kW",
        basis="cold-side volumetric flow x density x Cp x (Tout-Tin) / 3600",
        data_kind="CALCULATED",
        confidence="MEDIUM",
        approval_status="APPROVED",
        source_columns=("cold_flow", "cold_in", "cold_out", "crude_SG"),
        warnings=warnings,
        quality={"delta_t_c": delta_t},
    )


def calculate_q_norm(duty_kw: float, total_charge_m3_h: float) -> CalculationResult:
    if not math.isfinite(float(duty_kw)) or not math.isfinite(float(total_charge_m3_h)):
        raise ValueError("Q_norm inputs must be finite")
    if total_charge_m3_h <= 0:
        raise ValueError("Total charge must be positive")
    return CalculationResult(
        value=duty_kw / total_charge_m3_h,
        unit="kW per (m3/h)",
        basis="Q_kW / total crude charge",
        data_kind="CALCULATED",
        confidence="MEDIUM",
        approval_status="APPROVED",
        source_columns=("Q_kW", "total_charge"),
        warnings=("Throughput-normalized performance signal; not an approved Rf measurement.",),
    )
