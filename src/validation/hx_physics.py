"""HX physics diagnostics with explicit, unapproved denominator choice."""

import math

from src.governance import CalculationResult


def calculate_energy_balance_error(q_hot_kw: float, q_cold_kw: float) -> CalculationResult:
    if not math.isfinite(float(q_hot_kw)) or not math.isfinite(float(q_cold_kw)):
        raise ValueError("Energy-closure duties must be finite")
    reference = max(abs(float(q_hot_kw)), abs(float(q_cold_kw)))
    relative = None if reference == 0 else (float(q_hot_kw) - float(q_cold_kw)) / reference
    return CalculationResult(
        value=relative, unit="fraction", basis="(Q_hot-Q_cold)/max(|Q_hot|,|Q_cold|)",
        data_kind="CALCULATED", confidence="LOW", approval_status="CANDIDATE",
        source_columns=("Q_hot", "Q_cold"),
        warnings=("Diagnostic denominator and acceptance band require approval.",),
        quality={"is_valid": reference > 0, "warning_code": "ZERO_DUTY_REFERENCE" if reference == 0 else None,
                 "signed_error_kw": float(q_hot_kw) - float(q_cold_kw)},
    )
