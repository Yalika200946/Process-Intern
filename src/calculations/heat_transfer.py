"""Diagnostic LMTD/UA calculations; never promoted as canonical fouling evidence."""

import math

from src.governance import CalculationResult


def calculate_lmtd(delta_t1_c: float, delta_t2_c: float) -> CalculationResult:
    d1, d2 = float(delta_t1_c), float(delta_t2_c)
    if d1 <= 0 or d2 <= 0:
        raise ValueError("LMTD terminal differences must be positive")
    value = d1 if math.isclose(d1, d2) else (d1 - d2) / math.log(d1 / d2)
    return CalculationResult(
        value=value, unit="degC", basis="uncorrected counter-current LMTD",
        data_kind="CALCULATED", confidence="LOW", approval_status="CANDIDATE",
        source_columns=("deltaT1", "deltaT2"),
        warnings=("Diagnostic only; arrangement and correction factor are not approved.",),
    )


def calculate_ua(duty_kw: float, lmtd_c: float, correction_factor: float = 1.0) -> CalculationResult:
    if lmtd_c <= 0 or correction_factor <= 0:
        raise ValueError("LMTD and correction factor must be positive")
    return CalculationResult(
        value=float(duty_kw) / (float(lmtd_c) * float(correction_factor)), unit="kW/K",
        basis="Q / (F x LMTD)", data_kind="CALCULATED", confidence="LOW",
        approval_status="CANDIDATE", source_columns=("Q_kW", "LMTD", "F"),
        warnings=("Diagnostic only; exchanger arrangement/area require approval.",),
    )

