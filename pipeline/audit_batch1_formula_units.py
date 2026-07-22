"""Execute Batch-1 property/formula comparisons without promoting blocked quantities."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.calculations.heat_duty import calculate_heat_duty_from_enthalpy
from src.domain.crude_properties import calculate_crude_enthalpy_change


BASE = ROOT / "reports/tables/mvp_real_data"
OUT = BASE / "full_engineering_program/batch_01"


def compare_property_duty(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    valid = frame[
        frame.operating_valid.astype(bool)
        & frame.mass_flow_valid.astype(bool)
        & frame.q_cold_valid.astype(bool)
    ].copy()
    rows = []
    for row in valid.itertuples(index=False):
        enthalpy = calculate_crude_enthalpy_change(row.cold_in_c, row.cold_out_c, row.sg_15_6c)
        duty = calculate_heat_duty_from_enthalpy(row.mass_flow_value, enthalpy.value, stream_label="cold")
        rows.append({
            "timestamp": row.timestamp, "hx_id": row.hx_id,
            "property_model": enthalpy.quality["property_model"],
            "q_midpoint_cp_kw": row.q_cold_value,
            "q_integrated_cp_kw": duty.value,
            "difference_kw": duty.value - row.q_cold_value,
            "relative_difference_pct": (100.0 * (duty.value - row.q_cold_value) / row.q_cold_value
                                        if row.q_cold_value else np.nan),
            "status": "PROVISIONAL", "unit": "kW",
            "interpretation": "Analytic integral of the current linear Cp correlation; no property-model promotion."
        })
    detail = pd.DataFrame(rows)
    summary = detail.groupby("hx_id").agg(
        valid_records=("timestamp", "size"),
        median_q_midpoint_cp_kw=("q_midpoint_cp_kw", "median"),
        median_q_integrated_cp_kw=("q_integrated_cp_kw", "median"),
        max_absolute_difference_kw=("difference_kw", lambda values: values.abs().max()),
        max_absolute_relative_difference_pct=("relative_difference_pct", lambda values: values.abs().max()),
    ).reset_index()
    summary["status"] = "PROVISIONAL"
    summary["reason"] = "Linear Cp makes midpoint and analytic-integral duties numerically equivalent."
    return detail, summary


def unavailable_formula_registry() -> pd.DataFrame:
    return pd.DataFrame([
        {"quantity":"Qhot","status":"UNAVAILABLE","valid_records":0,
         "blocker":"MISSING_APPROVED_HOT_STREAM_FLOW_AND_PROPERTIES"},
        {"quantity":"Q_reconciled","status":"BLOCKED","valid_records":0,
         "blocker":"QHOT_AND_DUTY_UNCERTAINTIES_UNAVAILABLE"},
        {"quantity":"verified_U","status":"BLOCKED","valid_records":0,
         "blocker":"NO_VERIFIED_AREA_F_OR_ACTIVE_SHELL_BASIS"},
        {"quantity":"effectiveness","status":"BLOCKED","valid_records":0,
         "blocker":"HOT_SIDE_CAPACITY_RATE_UNAVAILABLE"},
        {"quantity":"energy_closure","status":"BLOCKED","valid_records":0,
         "blocker":"QHOT_UNAVAILABLE"},
    ])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    physics = pd.read_csv(BASE / "hx_physics_validation.csv", low_memory=False)
    detail, summary = compare_property_duty(physics)
    detail.to_csv(OUT / "property_duty_comparison_timeseries.csv", index=False)
    summary.to_csv(OUT / "property_duty_comparison_summary.csv", index=False)
    unavailable = unavailable_formula_registry()
    unavailable.to_csv(OUT / "blocked_formula_execution_registry.csv", index=False)

    areas = json.loads((ROOT / "config/area_and_f_registry.json").read_text(encoding="utf-8"))["records"]
    pd.DataFrame(areas).to_csv(OUT / "area_and_f_registry.csv", index=False)
    payload = {
        "batch": 1,
        "status": "IMPLEMENTED_NOT_VALIDATED",
        "real_data_valid_records": int(len(detail)),
        "hx_executed": int(detail.hx_id.nunique()),
        "maximum_property_approximation_difference_kw": float(detail.difference_kw.abs().max()),
        "maximum_property_approximation_difference_pct": float(detail.relative_difference_pct.abs().max()),
        "verified_u_records": 0,
        "qhot_records": 0,
        "raw_data_modified": False,
        "conclusion": "Formula framework completed where defensible; plant-basis quantities remain explicitly blocked."
    }
    (OUT / "batch_01_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
