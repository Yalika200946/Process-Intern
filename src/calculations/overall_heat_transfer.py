"""Evidence-gated conversion from UA to area-normalized U."""
from __future__ import annotations

import math

USABLE_AREA_STATUSES = {"VERIFIED_DESIGN_AREA", "VERIFIED_CALCULATION_AREA"}


def area_to_m2(value: float, unit: str) -> float:
    """Convert a positive area to m2; reject unknown or nonphysical inputs."""
    if not math.isfinite(float(value)) or float(value) <= 0:
        raise ValueError("Area must be finite and positive.")
    normalized = unit.strip().lower().replace("²", "2").replace(" ", "")
    if normalized in {"m2", "sqm"}:
        return float(value)
    if normalized in {"ft2", "sqft"}:
        return float(value) * 0.09290304
    raise ValueError(f"Unsupported or ambiguous area unit: {unit}")


def calculate_u_from_ua(*, ua_value: float, ua_unit: str, area_value: float,
                        area_unit: str, area_status: str, f_status: str,
                        shell_basis_matches: bool) -> dict:
    """Return UA unchanged and calculate U only with usable area and verified F."""
    result = {"ua_value": ua_value, "ua_unit": ua_unit, "area_value": area_value,
              "area_unit": area_unit, "area_status": area_status, "F_status": f_status,
              "u_value": None, "u_unit": "W/m2/K", "u_status": "UNAVAILABLE"}
    if ua_unit not in {"kW/K", "W/K"} or not math.isfinite(float(ua_value)):
        result["u_status"] = "INVALID_UA"
        return result
    if area_status not in USABLE_AREA_STATUSES:
        result["u_status"] = "REJECTED_AREA_EVIDENCE"
        return result
    if not shell_basis_matches:
        result["u_status"] = "CONFIGURATION_BASIS_MISMATCH"
        return result
    if f_status != "VERIFIED":
        result["u_status"] = "F_FACTOR_NOT_VERIFIED"
        return result
    try:
        area_m2 = area_to_m2(area_value, area_unit)
    except ValueError:
        result["u_status"] = "INVALID_OR_AMBIGUOUS_AREA_UNIT"
        return result
    ua_w_k = float(ua_value) * 1000 if ua_unit == "kW/K" else float(ua_value)
    result.update({"u_value": ua_w_k / area_m2, "u_status": "CALCULATED_FROM_VERIFIED_UA_AREA_F"})
    return result
