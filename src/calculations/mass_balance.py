"""Canonical mass-balance inference helpers."""

from __future__ import annotations

from src.governance import CalculationResult


def infer_e101g_flow(total_charge: float, e101ab: float, e101cd: float, e101ef: float) -> CalculationResult:
    raw = float(total_charge) - float(e101ab) - float(e101cd) - float(e101ef)
    warnings = () if raw >= 0 else ("Negative residual clipped to zero; check shared-flow allocation.",)
    return CalculationResult(
        value=max(0.0, raw), unit="m3/h",
        basis="total charge - E101AB - E101CD - E101EF branch flows",
        data_kind="INFERRED", confidence="LOW", approval_status="APPROVED",
        source_columns=("1fi005.pv", "1FI007.pv", "1FI008.pv", "1FI009.pv"),
        warnings=warnings,
        quality={"unclipped_residual_m3_h": raw},
    )
