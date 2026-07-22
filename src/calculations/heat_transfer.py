"""Diagnostic LMTD/UA calculations; never promoted as canonical fouling evidence."""

import math

from src.governance import CalculationResult


def calculate_lmtd(
    delta_t1_c: float,
    delta_t2_c: float,
    equal_tolerance_c: float = 0.0,
) -> CalculationResult:
    d1, d2 = float(delta_t1_c), float(delta_t2_c)
    if not all(math.isfinite(value) for value in (d1, d2, float(equal_tolerance_c))):
        raise ValueError("LMTD inputs must be finite")
    if d1 <= 0 or d2 <= 0:
        raise ValueError("LMTD terminal differences must be positive")
    if equal_tolerance_c < 0:
        raise ValueError("LMTD equal-difference tolerance must be non-negative")
    nearly_equal = math.isclose(d1, d2) if equal_tolerance_c == 0 else abs(d1 - d2) <= equal_tolerance_c
    value = (d1 + d2) / 2.0 if nearly_equal else (d1 - d2) / math.log(d1 / d2)
    return CalculationResult(
        value=value, unit="degC", basis="uncorrected counter-current LMTD",
        data_kind="CALCULATED", confidence="LOW", approval_status="CANDIDATE",
        source_columns=("deltaT1", "deltaT2"),
        warnings=("Diagnostic only; arrangement and correction factor are not approved.",),
        quality={"is_valid": True, "warning_code": None},
    )


def calculate_ua(duty_kw: float, lmtd_c: float, correction_factor: float = 1.0) -> CalculationResult:
    values = (float(duty_kw), float(lmtd_c), float(correction_factor))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("UA inputs must be finite")
    if lmtd_c <= 0 or correction_factor <= 0:
        raise ValueError("LMTD and correction factor must be positive")
    warning_code = "NEGATIVE_DUTY" if duty_kw < 0 else None
    reason = "Negative duty retained; check heat-duty sign and operating state." if warning_code else None
    return CalculationResult(
        value=float(duty_kw) / (float(lmtd_c) * float(correction_factor)), unit="kW/K",
        basis="Q / (F x LMTD)", data_kind="CALCULATED", confidence="LOW",
        approval_status="CANDIDATE", source_columns=("Q_kW", "LMTD", "F"),
        warnings=tuple(filter(None, (
            "Diagnostic only; exchanger arrangement/area require approval.", reason
        ))),
        quality={"is_valid": warning_code is None, "warning_code": warning_code, "reason": reason},
    )


def calculate_effectiveness(duty_kw: float, cold_capacity_rate_kw_k: float,
                            hot_capacity_rate_kw_k: float, hot_in_c: float,
                            cold_in_c: float) -> CalculationResult:
    """Calculate HX effectiveness only when both capacity rates are credible."""
    values = tuple(float(value) for value in (
        duty_kw, cold_capacity_rate_kw_k, hot_capacity_rate_kw_k, hot_in_c, cold_in_c
    ))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Effectiveness inputs must be finite")
    if cold_capacity_rate_kw_k <= 0 or hot_capacity_rate_kw_k <= 0:
        raise ValueError("Both capacity rates must be positive")
    driving = hot_in_c - cold_in_c
    if driving <= 0:
        raise ValueError("Hot inlet temperature must exceed cold inlet temperature")
    q_max = min(cold_capacity_rate_kw_k, hot_capacity_rate_kw_k) * driving
    value = duty_kw / q_max
    valid = 0.0 <= value <= 1.0
    reason = None if valid else "Effectiveness lies outside physical bounds; inputs or state require review."
    return CalculationResult(
        value=value, unit="fraction", basis="Q / (C_min x (T_hot,in - T_cold,in))",
        data_kind="CALCULATED", confidence="LOW", approval_status="CANDIDATE",
        source_columns=("Q_kW", "C_cold_kW_K", "C_hot_kW_K", "T_hot_in_C", "T_cold_in_C"),
        warnings=() if reason is None else (reason,),
        quality={"is_valid": valid, "warning_code": None if valid else "EFFECTIVENESS_OUT_OF_BOUNDS",
                 "reason": reason, "q_max_kw": q_max},
    )
