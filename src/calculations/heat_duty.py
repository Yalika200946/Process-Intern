"""Canonical cold-side heat-duty calculations with explicit provenance."""

from __future__ import annotations

import math

from src.governance import CalculationResult


def calculate_mass_flow(
    volumetric_flow_m3_h: float,
    density_kg_m3: float,
) -> CalculationResult:
    """Convert volumetric flow [m3/h] and density [kg/m3] to mass flow [kg/s]."""
    values = (volumetric_flow_m3_h, density_kg_m3)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("Mass-flow inputs must be finite")
    if volumetric_flow_m3_h < 0 or density_kg_m3 <= 0:
        raise ValueError("Volumetric flow must be non-negative and density must be positive")

    is_valid = volumetric_flow_m3_h > 0
    warning_code = None if is_valid else "ZERO_VOLUMETRIC_FLOW"
    warnings = () if is_valid else ("Zero volumetric flow; verify exchanger operating state.",)
    return CalculationResult(
        value=float(volumetric_flow_m3_h) * float(density_kg_m3) / 3600.0,
        unit="kg/s",
        basis="volumetric flow [m3/h] x density [kg/m3] / 3600",
        data_kind="CALCULATED",
        confidence="MEDIUM",
        approval_status="APPROVED",
        source_columns=("volumetric_flow_m3_h", "density_kg_m3"),
        warnings=warnings,
        quality={"is_valid": is_valid, "warning_code": warning_code},
    )


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
    if cp_kj_kg_k <= 0:
        raise ValueError("Cp must be positive")
    mass_flow = calculate_mass_flow(volumetric_flow_m3_h, density_kg_m3)
    delta_t = cold_out_c - cold_in_c
    duty_kw = mass_flow.value * cp_kj_kg_k * delta_t
    if delta_t < 0:
        warning_code = "NEGATIVE_COLD_SIDE_DELTA_T"
        reason = "Cold-side outlet is below inlet; check tags/state."
    elif mass_flow.quality["warning_code"]:
        warning_code = mass_flow.quality["warning_code"]
        reason = mass_flow.warnings[0]
    else:
        warning_code = None
        reason = None
    warnings = () if reason is None else (reason,)
    return CalculationResult(
        value=duty_kw,
        unit="kW",
        basis="cold-side volumetric flow x density x Cp x (Tout-Tin) / 3600",
        data_kind="CALCULATED",
        confidence="MEDIUM",
        approval_status="APPROVED",
        source_columns=("cold_flow", "cold_in", "cold_out", "crude_SG"),
        warnings=warnings,
        quality={
            "delta_t_c": delta_t,
            "mass_flow_kg_s": mass_flow.value,
            "is_valid": warning_code is None,
            "warning_code": warning_code,
            "reason": reason,
        },
    )


def calculate_heat_duty_from_enthalpy(
    mass_flow_kg_s: float,
    specific_enthalpy_change_kj_kg: float,
    *,
    stream_label: str = "unspecified",
) -> CalculationResult:
    """Calculate signed stream duty from mass flow and an enthalpy change."""
    values = (float(mass_flow_kg_s), float(specific_enthalpy_change_kj_kg))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Enthalpy-duty inputs must be finite")
    if mass_flow_kg_s < 0:
        raise ValueError("Mass flow must be non-negative")
    warning_code = None
    reason = None
    if mass_flow_kg_s == 0:
        warning_code, reason = "ZERO_MASS_FLOW", "Zero mass flow; verify stream operating state."
    elif specific_enthalpy_change_kj_kg < 0:
        warning_code, reason = "NEGATIVE_ENTHALPY_CHANGE", "Signed negative duty is preserved."
    return CalculationResult(
        value=float(mass_flow_kg_s) * float(specific_enthalpy_change_kj_kg),
        unit="kW", basis="mass flow [kg/s] x specific enthalpy change [kJ/kg]",
        data_kind="CALCULATED", confidence="MEDIUM", approval_status="CANDIDATE",
        source_columns=(f"{stream_label}_mass_flow_kg_s", f"{stream_label}_enthalpy_change_kj_kg"),
        warnings=() if reason is None else (reason,),
        quality={"is_valid": warning_code is None, "warning_code": warning_code,
                 "reason": reason, "stream_label": stream_label},
    )


def reconcile_heat_duties(q_cold_kw: float, q_hot_kw: float,
                           cold_uncertainty_kw: float, hot_uncertainty_kw: float) -> CalculationResult:
    """Inverse-variance reconciliation; requires explicit positive uncertainties."""
    values = tuple(float(value) for value in (q_cold_kw, q_hot_kw, cold_uncertainty_kw, hot_uncertainty_kw))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Duty-reconciliation inputs must be finite")
    if cold_uncertainty_kw <= 0 or hot_uncertainty_kw <= 0:
        raise ValueError("Duty uncertainties must be positive")
    wc, wh = 1.0 / cold_uncertainty_kw**2, 1.0 / hot_uncertainty_kw**2
    return CalculationResult(
        value=(wc * q_cold_kw + wh * q_hot_kw) / (wc + wh), unit="kW",
        basis="inverse-variance weighted reconciliation of credible cold and hot duties",
        data_kind="CALCULATED", confidence="LOW", approval_status="CANDIDATE",
        source_columns=("Q_cold_kW", "Q_hot_kW", "sigma_cold_kW", "sigma_hot_kW"),
        warnings=("Use only when both duties and uncertainty bases are credible.",),
        quality={"is_valid": True, "warning_code": None},
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
