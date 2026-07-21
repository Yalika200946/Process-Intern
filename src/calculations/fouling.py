"""Keep clean-equivalent performance, fouling indicator, and fouling rate distinct."""

from __future__ import annotations

from src.governance import CalculationResult
from src.validation.nb_audit import robust_fouling_rate


def calculate_fouling_indicators(actual: float, clean_equivalent: float) -> dict:
    if clean_equivalent <= 0:
        raise ValueError("clean_equivalent must be positive")
    return {
        "performance_ratio": CalculationResult(
            actual / clean_equivalent, "fraction", "actual / clean-equivalent performance",
            "CALCULATED", "MEDIUM", "CANDIDATE", ("actual", "clean_equivalent")
        ).to_dict(),
        "duty_shortfall": CalculationResult(
            max(0.0, clean_equivalent - actual), None,
            "max(0, clean-equivalent - actual)", "CALCULATED", "MEDIUM", "CANDIDATE",
            ("actual", "clean_equivalent")
        ).to_dict(),
    }


def estimate_fouling_rate(days, u_relative, rf, state=None, **kwargs):
    result = robust_fouling_rate(days, u_relative, rf_run=rf, state=state, **kwargs)
    return {**result, "approval_status": "CANDIDATE", "data_kind": "CALCULATED"}

