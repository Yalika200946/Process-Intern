"""Keep clean-equivalent performance, fouling indicator, and fouling rate distinct."""

from __future__ import annotations

import math

from src.governance import CalculationResult
from src.validation.nb_audit import robust_fouling_rate


def _indicator_result(value, basis, *, warning_code=None, reason=None):
    return CalculationResult(
        value=value,
        unit="fraction",
        basis=basis,
        data_kind="CALCULATED",
        confidence="MEDIUM",
        approval_status="CANDIDATE",
        source_columns=("UA_actual", "UA_clean"),
        warnings=() if reason is None else (reason,),
        quality={"is_valid": value is not None, "warning_code": warning_code, "reason": reason},
    ).to_dict()


def calculate_fouling_indicators(
    actual: float,
    clean_equivalent: float,
    *,
    operating_valid: bool = True,
) -> dict:
    """Return dimensionless MVP UA-normalized performance and fouling index."""
    if not math.isfinite(float(clean_equivalent)) or clean_equivalent <= 0:
        raise ValueError("clean_equivalent must be positive")
    if not operating_valid:
        reason = "Actual UA record is not valid for the configured operating state."
        normalized = _indicator_result(None, "UA_actual / UA_clean",
                                       warning_code="INVALID_OPERATING_RECORD", reason=reason)
        fouling_index = _indicator_result(None, "1 - (UA_actual / UA_clean)",
                                          warning_code="INVALID_OPERATING_RECORD", reason=reason)
    elif not math.isfinite(float(actual)):
        reason = "Actual UA is non-finite."
        normalized = _indicator_result(None, "UA_actual / UA_clean",
                                       warning_code="NONFINITE_ACTUAL_UA", reason=reason)
        fouling_index = _indicator_result(None, "1 - (UA_actual / UA_clean)",
                                          warning_code="NONFINITE_ACTUAL_UA", reason=reason)
    else:
        normalized_value = float(actual) / float(clean_equivalent)
        above_clean = normalized_value > 1.0
        code = "ABOVE_CLEAN_BASELINE" if above_clean else None
        reason = ("Actual UA is above the clean baseline; value is preserved without clipping."
                  if above_clean else None)
        normalized = _indicator_result(normalized_value, "UA_actual / UA_clean",
                                       warning_code=code, reason=reason)
        fouling_index = _indicator_result(1.0 - normalized_value,
                                          "1 - (UA_actual / UA_clean)",
                                          warning_code=code, reason=reason)

    shortfall_value = (None if normalized["value"] is None
                       else max(0.0, float(clean_equivalent) - float(actual)))
    shortfall_reason = "Legacy input basis does not declare an absolute UA unit."
    duty_shortfall = CalculationResult(
        shortfall_value, None, "max(0, clean-equivalent - actual)",
        "CALCULATED", "MEDIUM", "CANDIDATE", ("actual", "clean_equivalent"),
        warnings=(shortfall_reason,),
        quality={
            "is_valid": shortfall_value is not None,
            "warning_code": None if shortfall_value is not None else normalized["quality"]["warning_code"],
            "reason": shortfall_reason,
        },
    ).to_dict()
    return {
        "ua_normalized": normalized,
        "fouling_index": fouling_index,
        "performance_ratio": normalized,
        "duty_shortfall": duty_shortfall,
    }


def estimate_fouling_rate(days, u_relative, rf, state=None, **kwargs):
    result = robust_fouling_rate(days, u_relative, rf_run=rf, state=state, **kwargs)
    return {**result, "approval_status": "CANDIDATE", "data_kind": "CALCULATED"}
