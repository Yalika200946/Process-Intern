"""Local single-HX equivalent crude-temperature impact for the CPHT MVP."""

from __future__ import annotations

import math
from collections.abc import Mapping


IMPACT_BASIS = "single_hx_equivalent_crude_temperature_gain"
NETWORK_ASSUMPTION = (
    "Local single-HX equivalent only; full CPHT network effects, downstream compensation, "
    "split/mix behavior, bypass, and exchanger interactions are not included."
)


def _scalar(value, name: str) -> float:
    """Accept a scalar, CalculationResult, or calculation-result mapping."""
    if hasattr(value, "value"):
        value = value.value
    elif isinstance(value, Mapping):
        value = value.get("value", value.get("clean_ua"))
    if isinstance(value, (list, tuple, set, dict)):
        raise ValueError(f"{name} must be one scalar single-HX value")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be one scalar single-HX value") from exc


def _result(*, q_actual=None, q_clean=None, q_signed=None, q_recoverable=None,
            cit_gain=None, valid: bool, code: str | None, reason: str | None,
            assumptions=()) -> dict:
    warnings = () if reason is None else (reason,)
    return {
        "q_actual": q_actual,
        "q_clean_expected": q_clean,
        "q_deficit_signed": q_signed,
        "q_recoverable": q_recoverable,
        "cit_gain_equivalent": cit_gain,
        "units": {
            "q_actual": "kW",
            "q_clean_expected": "kW",
            "q_deficit_signed": "kW",
            "q_recoverable": "kW",
            "cit_gain_equivalent": "K",
            "crude_mass_flow": "kg/s",
            "crude_cp": "kJ/kg-K",
        },
        "basis": "max(UA_clean x F x LMTD_current - Q_actual, 0) / (m_crude x Cp_crude)",
        "impact_basis": IMPACT_BASIS,
        "data_kind": "CALCULATED",
        "assumptions": (NETWORK_ASSUMPTION, *tuple(assumptions)),
        "warnings": warnings,
        "quality": {"is_valid": valid, "warning_code": code, "reason": reason},
    }


def calculate_single_hx_cit_impact(
    actual_duty_kw,
    crude_mass_flow_kg_s,
    crude_cp_kj_kg_k,
    *,
    clean_ua_kw_k=None,
    lmtd_current_k=None,
    correction_factor: float = 1.0,
    expected_clean_duty_kw=None,
    operating_valid: bool = True,
) -> dict:
    """Calculate recoverable duty and its local equivalent crude-temperature gain.

    Supply either ``expected_clean_duty_kw`` directly or both ``clean_ua_kw_k`` and
    ``lmtd_current_k``.  Inputs may be scalars or canonical result objects/mappings.
    No collection of exchangers is accepted or summed.
    """
    if not operating_valid:
        reason = "HX record is not valid for the configured operating state."
        return _result(valid=False, code="INVALID_OPERATING_RECORD", reason=reason)

    q_actual = _scalar(actual_duty_kw, "actual_duty_kw")
    if not math.isfinite(q_actual) or q_actual < 0:
        return _result(q_actual=q_actual, valid=False, code="INVALID_ACTUAL_DUTY",
                       reason="Actual duty must be a finite non-negative single-HX value.")

    if expected_clean_duty_kw is not None:
        q_clean = _scalar(expected_clean_duty_kw, "expected_clean_duty_kw")
        if not math.isfinite(q_clean) or q_clean < 0:
            return _result(q_actual=q_actual, q_clean=q_clean, valid=False,
                           code="INVALID_CLEAN_UA",
                           reason="Expected clean duty must be finite and non-negative.")
        assumptions = ("Expected clean duty was supplied directly by the caller.",)
    else:
        clean_ua = _scalar(clean_ua_kw_k, "clean_ua_kw_k")
        if not math.isfinite(clean_ua) or clean_ua <= 0:
            return _result(q_actual=q_actual, valid=False, code="INVALID_CLEAN_UA",
                           reason="Clean UA must be finite and positive in kW/K.")
        lmtd = _scalar(lmtd_current_k, "lmtd_current_k")
        if not math.isfinite(lmtd) or lmtd <= 0:
            return _result(q_actual=q_actual, valid=False, code="INVALID_LMTD",
                           reason="Current LMTD must be finite and positive in K.")
        factor = _scalar(correction_factor, "correction_factor")
        if not math.isfinite(factor) or factor <= 0:
            return _result(q_actual=q_actual, valid=False,
                           code="INVALID_CORRECTION_FACTOR",
                           reason="Correction factor must be finite and positive.")
        q_clean = clean_ua * factor * lmtd
        assumptions = ("Clean UA is constant over the current LMTD and correction-factor basis.",)

    mass_flow = _scalar(crude_mass_flow_kg_s, "crude_mass_flow_kg_s")
    if not math.isfinite(mass_flow) or mass_flow <= 0:
        return _result(q_actual=q_actual, q_clean=q_clean, valid=False,
                       code="INVALID_MASS_FLOW",
                       reason="Crude mass flow must be finite and positive in kg/s.")
    cp = _scalar(crude_cp_kj_kg_k, "crude_cp_kj_kg_k")
    if not math.isfinite(cp) or cp <= 0:
        return _result(q_actual=q_actual, q_clean=q_clean, valid=False,
                       code="INVALID_CRUDE_CP",
                       reason="Crude Cp must be finite and positive in kJ/kg-K.")

    signed = q_clean - q_actual
    recoverable = max(signed, 0.0)
    gain = recoverable / (mass_flow * cp)
    if signed < 0:
        code = "ACTUAL_DUTY_ABOVE_CLEAN_EXPECTATION"
        reason = "Actual duty exceeds expected clean duty; signed difference is retained and recoverable duty is zero."
    elif recoverable == 0:
        code = "NO_RECOVERABLE_DUTY"
        reason = "Actual duty equals expected clean duty; no recoverable duty is indicated."
    else:
        code = None
        reason = None
    return _result(q_actual=q_actual, q_clean=q_clean, q_signed=signed,
                   q_recoverable=recoverable, cit_gain=gain, valid=True,
                   code=code, reason=reason, assumptions=assumptions)
