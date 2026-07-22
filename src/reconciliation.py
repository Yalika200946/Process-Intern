"""Small uncertainty-weighted reconciliation primitives for auditable pilots."""
from __future__ import annotations

import numpy as np


def reconcile_linear_equality(measured_values, uncertainties, coefficients, *, rhs: float = 0.0) -> dict:
    """Weighted least-squares projection onto one exact linear equality.

    Minimizes sum(((x-y)/sigma)**2) subject to coefficients @ x = rhs.
    Raw measurements are returned unchanged alongside reconciled values.
    """
    y = np.asarray(measured_values, dtype=float)
    sigma = np.asarray(uncertainties, dtype=float)
    a = np.asarray(coefficients, dtype=float)
    if not (len(y) and len(y) == len(sigma) == len(a)):
        return {"quality": {"is_valid": False, "warning_code": "NOT_IDENTIFIABLE", "reason": "Input lengths differ or are empty."}}
    if not (np.isfinite(y).all() and np.isfinite(sigma).all() and np.isfinite(a).all() and np.isfinite(rhs)):
        return {"quality": {"is_valid": False, "warning_code": "BLOCKED_BY_DATA", "reason": "Non-finite reconciliation input."}}
    if (sigma <= 0).any() or not np.any(a):
        return {"quality": {"is_valid": False, "warning_code": "NOT_IDENTIFIABLE", "reason": "Positive uncertainties and a nonzero constraint are required."}}
    variances = sigma ** 2
    denominator = float(np.sum((a ** 2) * variances))
    residual_before = float(a @ y - rhs)
    adjustment = -(variances * a) * residual_before / denominator
    reconciled = y + adjustment
    residual_after = float(a @ reconciled - rhs)
    normalized = residual_before / denominator ** 0.5
    positive = bool((reconciled > 0).all())
    return {
        "measured_values": y.tolist(), "reconciled_values": reconciled.tolist(),
        "reconciliation_adjustments": adjustment.tolist(), "measurement_uncertainties": sigma.tolist(),
        "constraint_residual_before": residual_before, "constraint_residual_after": residual_after,
        "normalized_residual": normalized, "chi_square": float(np.sum((adjustment / sigma) ** 2)),
        "reconciliation_status": "RECONCILED_PROVISIONAL" if positive else "CONSTRAINT_CONFLICT",
        "identifiability_status": "INFERRED_IDENTIFIABLE", "data_kind": "RECONCILED",
        "quality": {"is_valid": positive, "warning_code": "" if positive else "CONSTRAINT_CONFLICT",
                    "reason": "Exact weighted projection with explicit candidate uncertainties."},
    }


def reconcile_branch_flow_balance(total_flow, branch_flows, total_uncertainty, branch_uncertainties) -> dict:
    values = list(branch_flows) + [total_flow]
    uncertainties = list(branch_uncertainties) + [total_uncertainty]
    result = reconcile_linear_equality(values, uncertainties, [1.0] * len(branch_flows) + [-1.0])
    result["basis"] = "sum(reconciled branch flows) = reconciled total flow"
    result["unit"] = "m3/h"
    return result


def reconcile_common_value(measured_value, calculated_value, measured_uncertainty, calculated_uncertainty) -> dict:
    """Reconcile two estimates of one state without overwriting either input."""
    result = reconcile_linear_equality(
        [measured_value, calculated_value], [measured_uncertainty, calculated_uncertainty], [1.0, -1.0]
    )
    if result.get("quality", {}).get("is_valid"):
        shared = float(np.mean(result["reconciled_values"]))
        result["reconciled_value"] = shared
        result["measured_value"] = float(measured_value)
        result["calculated_value"] = float(calculated_value)
    result["basis"] = "uncertainty-weighted common-state reconciliation"
    return result
