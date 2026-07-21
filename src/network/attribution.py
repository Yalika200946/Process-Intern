"""Traceable local-condition versus network-consequence diagnostics.

This is intentionally not a thermal digital twin. It combines observed
Q-normalised condition with audited single-HX CIT recovery. Pair and multi-HX
interaction terms remain unestimated until a network model passes backtesting.
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping


def equivalent_furnace_duty_mw(cit_recovery_c: float, charge_m3_h: float,
                               density_kg_m3: float = 850.0,
                               cp_kj_kg_k: float = 2.2) -> float:
    """Convert CIT recovery to avoided furnace duty using the cold-side basis."""
    if min(cit_recovery_c, charge_m3_h, density_kg_m3, cp_kj_kg_k) < 0:
        raise ValueError("CIT recovery, charge, density and Cp must be non-negative")
    return charge_m3_h * density_kg_m3 * cp_kj_kg_k * cit_recovery_c / 3600.0 / 1000.0


def compensation_ratio(local_q_loss_mw: float, equivalent_cit_duty_mw: float) -> float | None:
    """Return 1 - CIT-equivalent duty/local loss; None for unusable denominator."""
    if local_q_loss_mw <= 0 or not math.isfinite(local_q_loss_mw):
        return None
    return 1.0 - equivalent_cit_duty_mw / local_q_loss_mw


def evidence_confidence(source: str | None, n_events: int | None) -> str:
    if source == "measured" and (n_events or 0) >= 3:
        return "HIGH"
    if source == "measured" and (n_events or 0) >= 1:
        return "MEDIUM"
    if source in {"model_calibrated", "predicted"}:
        return "LOW"
    return "INSUFFICIENT"


def build_network_diagnostics(condition_rows: Iterable[Mapping],
                              consequence_by_hx: Mapping[str, Mapping], *,
                              charge_m3_h: float, density_kg_m3: float = 850.0,
                              cp_kj_kg_k: float = 2.2) -> list[dict]:
    """Join local Q condition with single-clean CIT consequence without summing it."""
    output: list[dict] = []
    for condition in condition_rows:
        hx = str(condition["HX"])
        consequence = consequence_by_hx.get(hx, {})
        clean, current = condition.get("clean_q_norm"), condition.get("current_q_norm")
        local_loss_mw = condition_loss_fraction = None
        if clean is not None and current is not None and clean > 0:
            local_loss_mw = max(0.0, float(clean) - float(current)) * charge_m3_h / 1000.0
            condition_loss_fraction = max(0.0, (float(clean) - float(current)) / float(clean))
        cit = consequence.get("cit_gain_C")
        eq_mw = (equivalent_furnace_duty_mw(float(cit), charge_m3_h, density_kg_m3, cp_kj_kg_k)
                 if cit is not None and float(cit) >= 0 else None)
        cr = compensation_ratio(local_loss_mw, eq_mw) if eq_mw is not None and local_loss_mw is not None else None
        warnings: list[str] = []
        if cit is None:
            warnings.append("NO_SINGLE_HX_CIT_ESTIMATE")
        if local_loss_mw is None or local_loss_mw <= 0:
            warnings.append("LOCAL_Q_LOSS_NOT_ESTIMABLE")
        if cr is not None and (cr < 0 or cr > 1):
            warnings.append("COMPENSATION_OUTSIDE_NOMINAL_RANGE_REVIEW_MODEL_OR_REDISTRIBUTION")
        output.append({
            "HX": hx,
            "local_q_loss_mw": None if local_loss_mw is None else round(local_loss_mw, 4),
            "condition_loss_fraction": None if condition_loss_fraction is None else round(condition_loss_fraction, 4),
            "marginal_cit_recovery_c": None if cit is None else round(float(cit), 4),
            "cit_equivalent_duty_mw": None if eq_mw is None else round(eq_mw, 4),
            "compensation_ratio": None if cr is None else round(cr, 4),
            "cit_evidence_source": consequence.get("cit_gain_source"),
            "cit_evidence_events": consequence.get("cit_gain_n_events"),
            "confidence": evidence_confidence(consequence.get("cit_gain_source"), consequence.get("cit_gain_n_events")),
            "data_kind": "CALCULATED", "approval_status": "CANDIDATE", "warnings": warnings,
        })
    return output
