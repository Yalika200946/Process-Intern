"""Evidence-first correction batch for the CPHT-2 pilot.

This layer does not alter raw measurements, infer replacement tags, confirm
cleaning events, or promote the pilot branch without an approved tolerance.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.network.datasheet import read_datasheet_diagnostics

BASE = ROOT / "reports/tables/mvp_real_data"
OUT = BASE / "critical_correction"
FIG = ROOT / "reports/figures/mvp_real_data/critical_correction"
DATA = Path(r"C:\Desktop\Bangchak Internship 2026\Data")
CPHT2 = ["E106AB", "E110ABC", "E103AB", "E107AB", "E111", "E104",
         "E108AB", "E112AB", "E105AB", "E112C", "E109AB", "E113A"]
MAPPING_BLOCKERS = {
    "E105AB": "TAG_REGISTER_CONFLICT_HOT_IN_1TI196_SELECTED",
    "E107AB": "ELEVATED_COLD_TEMPERATURE_VIOLATIONS",
    "E108AB": "CONFIGURATION_AMBIGUITY_AND_INVALID_TEMPERATURE_PERIODS",
    "E112AB": "SHARED_RESIDUE_INLET_INFERENCE",
    "E112C": "TOPOLOGY_AND_TERMINAL_TEMPERATURE_CONFLICT",
    "E113A": "E112C_NETWORK_OVERLAP_NOT_INCLUDED",
}


def issue_periods(physics: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("E103AB", "1TI225.pv", "SENSOR_FLATLINE", "sensor fault"),
        ("E106AB", "1TI225.pv", "SENSOR_FLATLINE", "sensor fault"),
        ("E101EF", "temperature quartet", "IMPOSSIBLE_TEMPERATURE_RELATIONSHIP", "unresolved evidence"),
        ("E107AB", "temperature quartet", "IMPOSSIBLE_TEMPERATURE_RELATIONSHIP", "unresolved evidence"),
        ("E108AB", "temperature quartet", "IMPOSSIBLE_TEMPERATURE_RELATIONSHIP", "configuration change or unresolved evidence"),
    ]
    rows = []
    for hx, tags, code, cause in specs:
        x = physics[physics.hx_id.eq(hx)].sort_values("timestamp")
        hit = x.quality_warning_code.fillna("").str.contains(code, regex=False)
        groups = hit.ne(hit.shift()).cumsum()
        for _, period in x[hit].groupby(groups[hit]):
            rows.append({"hx_id": hx, "affected_tags": tags, "warning_code": code,
                         "period_start": period.timestamp.min(), "period_end": period.timestamp.max(),
                         "record_count": len(period), "cause_class": cause,
                         "replacement_used": False, "interpolation_used": False,
                         "regenerate_q_lmtd_ua": True, "regenerate_reference_cit": True})
    for hx, warning in MAPPING_BLOCKERS.items():
        rows.append({"hx_id": hx, "affected_tags": "see config/mvp_real_data_pilot.json",
                     "warning_code": warning, "period_start": physics.timestamp.min(),
                     "period_end": physics.timestamp.max(), "record_count": int((physics.hx_id == hx).sum()),
                     "cause_class": "tag mapping" if hx == "E105AB" else "configuration change or unresolved evidence",
                     "replacement_used": False, "interpolation_used": False,
                     "regenerate_q_lmtd_ua": True, "regenerate_reference_cit": True})
    return pd.DataFrame(rows)


def area_f_audit(config: dict, diagnostics: dict) -> pd.DataFrame:
    rows = []
    for hx, spec in config["heat_exchangers"].items():
        if spec.get("status") in {"BLOCKED", "UNAVAILABLE"}:
            rows.append({"hx_id": hx, "area_available": False, "area_source": "UNAVAILABLE",
                         "area_unit": "m2", "F_available": False, "F_source": "UNAVAILABLE",
                         "F_by_configuration": False, "current_metric_name": "UNAVAILABLE",
                         "current_unit": "", "corrected_metric_name": "UNAVAILABLE",
                         "corrected_unit": "", "numerical_change_required": False, "status": spec["status"]})
            continue
        ds = diagnostics.get(hx)
        sheets = ds["sheets"] if ds else []
        ds_area = sum(s["area_m2"] for s in sheets if s.get("area_m2")) or None
        configured = spec.get("area_m2")
        area_ok = ds_area is not None
        match = area_ok and np.isclose(float(configured), float(ds_area))
        rows.append({"hx_id": hx, "area_available": area_ok,
                     "area_source": "Data Sheet Heat Exchanger.xlsx" if area_ok else "NO_DATASHEET_SHEET",
                     "area_unit": "m2", "configured_area_m2": configured, "datasheet_group_area_m2": ds_area,
                     "F_available": False, "F_source": "F=1.0 ASSUMPTION ONLY",
                     "F_by_configuration": False, "current_metric_name": "apparent_UA_F1",
                     "current_unit": "kW/K", "corrected_metric_name": "UA after approved F; U only after approved group area",
                     "corrected_unit": "kW/K; W/m2/K", "numerical_change_required": not match or not area_ok,
                     "status": "AREA_MISMATCH_REQUIRES_REVIEW" if area_ok and not match else
                               "F_FACTOR_REQUIRES_APPROVAL" if area_ok else "AREA_AND_F_REQUIRED"})
    return pd.DataFrame(rows)


def cpht2_reference_review(physics: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for hx in CPHT2:
        x = physics[physics.hx_id.eq(hx)]
        valid = x[x.operating_valid.astype(bool) & x.ua_valid.astype(bool) & x.ua_value.gt(0)]
        c = candidates[candidates.hx_id.eq(hx)].copy()
        blocker = MAPPING_BLOCKERS.get(hx)
        if hx == "E112C": status = "BLOCKED_BY_TOPOLOGY"
        elif hx in ("E103AB", "E106AB") and len(valid) < 100: status = "BLOCKED_BY_SENSOR"
        elif blocker: status = "BLOCKED_BY_CONFIGURATION"
        elif c.empty: status = "INSUFFICIENT_DATA"
        else: status = "CANDIDATE_REFERENCE_REQUIRES_REVIEW"
        best = c.sort_values(["ua_variability_cv", "crude_flow_variability_cv"]).head(1)
        row = {"hx_id": hx, "status": status, "valid_record_count": len(valid),
               "candidate_count": len(c), "mapping_or_configuration_blocker": blocker or "",
               "clean_condition_confirmed": False, "cleaning_event_confirmed": False,
               "evidence_for_reference": "Stable operating-valid UA/flow/temperature window exists." if len(c) else "",
               "evidence_against_reference": "No maintenance confirmation; operating-condition matching remains required."}
        if not best.empty:
            b = best.iloc[0]
            row.update({"candidate_start": b.candidate_start, "candidate_end": b.candidate_end,
                        "candidate_records": b.valid_record_count, "candidate_u_w_m2_k_legacy": b.median_ua_w_m2_k,
                        "ua_cv": b.ua_variability_cv, "flow_cv": b.crude_flow_variability_cv,
                        "temperature_stability_c": b.temperature_stability_mean_std_c})
        rows.append(row)
    result = pd.DataFrame(rows)
    eligible = result[result.status.eq("CANDIDATE_REFERENCE_REQUIRES_REVIEW")]
    result["recommended_pilot"] = False
    if not eligible.empty:
        # Prefer branch-15 continuity and high valid coverage; never auto-approve the reference.
        preferred = eligible[eligible.hx_id.eq("E104")]
        pick = preferred.index[0] if len(preferred) else eligible.valid_record_count.idxmax()
        result.loc[pick, "recommended_pilot"] = True
    return result


def reference_sensitivity_and_conditions(physics: pd.DataFrame, review: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    sensitivity, comparisons = [], []
    for _, row in review.dropna(subset=["candidate_start", "candidate_end"]).iterrows():
        g = physics[physics.hx_id.eq(row.hx_id) & physics.operating_valid.astype(bool) & physics.ua_valid.astype(bool)].copy()
        g["timestamp"] = pd.to_datetime(g.timestamp)
        start, end = pd.Timestamp(row.candidate_start), pd.Timestamp(row.candidate_end)
        for ds in (-3, 0, 3):
            for de in (-3, 0, 3):
                w = g[g.timestamp.between(start + pd.Timedelta(days=ds), end + pd.Timedelta(days=de))]
                sensitivity.append({"hx_id": row.hx_id, "start_shift_days": ds, "end_shift_days": de,
                                    "valid_records": len(w), "median_apparent_ua_f1_kw_k": w.ua_value.median(),
                                    "status": "SENSITIVITY_ONLY_NOT_AUTO_SELECTED"})
        spans = {"PRE": (start - pd.Timedelta(days=30), start - pd.Timedelta(days=1)),
                 "REFERENCE_CANDIDATE": (start, end),
                 "POST": (end + pd.Timedelta(days=1), end + pd.Timedelta(days=30))}
        for label, (a, b) in spans.items():
            w = g[g.timestamp.between(a, b)]
            comparisons.append({"hx_id": row.hx_id, "period": label, "start": a, "end": b,
                                "valid_records": len(w), "median_apparent_ua_f1_kw_k": w.ua_value.median(),
                                "median_flow_m3_h": w.cold_flow_m3_h.median(), "median_lmtd_c": w.lmtd_value.median(),
                                "median_hot_in_c": w.hot_in_c.median(), "median_sg_15_6c": w.sg_15_6c.median(),
                                "interpretation": "Operating-condition comparison; not cleaning attribution."})
    return pd.DataFrame(sensitivity), pd.DataFrame(comparisons)


def corrected_performance_outputs(physics: pd.DataFrame) -> pd.DataFrame:
    """Use apparent UA at explicit F=1; never calculate area-dependent U here."""
    rows=[]; directory=FIG/"corrected_apparent_ua"; directory.mkdir(parents=True,exist_ok=True)
    for hx_id,g in physics.groupby("hx_id"):
        valid=g[g.operating_valid.astype(bool)&g.ua_valid.astype(bool)&g.ua_value.notna()].sort_values("timestamp")
        rows.append({"hx_id":hx_id,"total_records":len(g),"valid_records":len(valid),
                     "valid_coverage_pct":100*len(valid)/len(g) if len(g) else 0,
                     "median_q_cold_kw":valid.q_cold_value.median(),"iqr_q_cold_kw":valid.q_cold_value.quantile(.75)-valid.q_cold_value.quantile(.25),
                     "median_lmtd_c":valid.lmtd_value.median(),"iqr_lmtd_c":valid.lmtd_value.quantile(.75)-valid.lmtd_value.quantile(.25),
                     "median_apparent_ua_f1_kw_k":valid.ua_value.median(),"iqr_apparent_ua_f1_kw_k":valid.ua_value.quantile(.75)-valid.ua_value.quantile(.25),
                     "metric_status":"PROVISIONAL_F_FACTOR","u_w_m2_k_status":"BLOCKED_PENDING_VERIFIED_GROUP_AREA"})
        if len(valid):
            fig,ax=plt.subplots(figsize=(14,4));ax.plot(valid.timestamp,valid.ua_value,lw=.7)
            ax.set(xlabel="Time (Asia/Bangkok)",ylabel="Apparent UA at F=1 (kW/K)",title=f"{hx_id} - corrected non-area metric")
            ax.grid(alpha=.2);fig.tight_layout();fig.savefig(directory/f"{hx_id}_apparent_ua_f1.png",dpi=140);plt.close(fig)
    return pd.DataFrame(rows)


def validate_branch_15(physics: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = ["cold_flow_m3_h", "cold_in_c", "cold_out_c", "hot_in_c", "hot_out_c", "sg_15_6c", "operating_valid"]
    a = physics[physics.hx_id.eq("E103AB")].set_index("timestamp")[cols]
    b = physics[physics.hx_id.eq("E104")].set_index("timestamp")[cols]
    joined = a.join(b, lsuffix="_103", rsuffix="_104", how="inner")
    joined = joined[joined.operating_valid_103.astype(bool) & joined.operating_valid_104.astype(bool)].dropna()
    split = int(len(joined) * 0.8)
    train, test = joined.iloc[:split], joined.iloc[split:]
    f103 = ["cold_flow_m3_h_103", "cold_in_c_103", "hot_in_c_103", "hot_out_c_103", "sg_15_6c_103"]
    f104 = ["cold_flow_m3_h_104", "cold_in_c_104", "hot_in_c_104", "hot_out_c_104", "sg_15_6c_104"]
    m103 = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(train[f103], train.cold_out_c_103)
    pred103 = m103.predict(test[f103])
    m104 = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(train[f104], train.cold_out_c_104)
    propagated = test[f104].copy(); propagated["cold_in_c_104"] = pred103
    pred104 = m104.predict(propagated)
    ts = pd.DataFrame({"timestamp": test.index, "measured_e103_out_c": test.cold_out_c_103,
                       "predicted_e103_out_c": pred103, "measured_e104_out_c": test.cold_out_c_104,
                       "predicted_e104_out_c": pred104, "throughput_m3_h": test.cold_flow_m3_h_103})
    rows = []
    for node, measured, predicted in [("E103_OUT/E104_IN", ts.measured_e103_out_c, ts.predicted_e103_out_c),
                                       ("E104_OUT", ts.measured_e104_out_c, ts.predicted_e104_out_c)]:
        err = predicted - measured
        rows.append({"pilot_branch": "branch_15_partial_E103AB_E104", "node": node,
                     "train_cases": len(train), "valid_test_cases": len(test), "mae_c": float(err.abs().mean()),
                     "bias_c": float(err.mean()), "rmse_c": float(np.sqrt((err**2).mean())),
                     "validation_method": "chronological_80_20_holdout_sequential_propagation",
                     "engineering_tolerance_c": None, "status": "ENGINEERING_THRESHOLD_REQUIRED",
                     "topology_status": "MEASURED_TAG_CONTINUITY",
                     "limitations": "E105AB excluded due hot-in tag conflict; no split/mix or total-CIT claim."})
    return ts, pd.DataFrame(rows)


def maintenance_evidence() -> pd.DataFrame:
    rows = []
    sources = [(DATA / "Cleaning_Events.csv", "DERIVED_SIGNAL_TABLE"),
               (DATA / "Cleaning_Event_Validation.csv", "DERIVED_ANALYTICAL_TABLE")]
    for path, kind in sources:
        if not path.exists(): continue
        frame = pd.read_csv(path)
        hx_col = "HX" if "HX" in frame else "hx_id"
        date_col = "date" if "date" in frame else "event_date"
        type_col = "type" if "type" in frame else "event_type"
        for _, row in frame.iterrows():
            rows.append({"hx_id": row.get(hx_col), "event_date": row.get(date_col),
                         "event_type": row.get(type_col), "evidence_source": str(path),
                         "evidence_strength": kind, "clean_condition_confirmed": False,
                         "cleaning_event_confirmed": False, "usable_for_baseline": False,
                         "limitations": "Generated analytical evidence; no work order or individual-HX maintenance record."})
    # The bypass list is authoritative for feasibility, not evidence that an event occurred.
    rows.append({"hx_id": "ALL_LISTED_HX", "event_date": None, "event_type": "BYPASS_CAPABILITY",
                 "evidence_source": str(DATA / "list bypass Cleaning Heat Exchanger.xlsx"),
                 "evidence_strength": "ENGINEER_FEASIBILITY_REFERENCE", "clean_condition_confirmed": False,
                 "cleaning_event_confirmed": False, "usable_for_baseline": False,
                 "limitations": "Capability list does not prove a cleaning event date."})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True); FIG.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / "config/mvp_real_data_pilot.json").read_text(encoding="utf-8"))
    physics = pd.read_csv(BASE / "hx_physics_validation.csv", parse_dates=["timestamp"])
    candidates = pd.read_csv(BASE / "candidate_stable_periods.csv", parse_dates=["candidate_start", "candidate_end"])
    issues = issue_periods(physics); issues.to_csv(OUT / "corrected_issue_register.csv", index=False)
    diagnostics = read_datasheet_diagnostics(DATA / "Data Sheet Heat Exchanger.xlsx")
    area = area_f_audit(config, diagnostics); area.to_csv(OUT / "area_f_factor_audit.csv", index=False)
    refs = cpht2_reference_review(physics, candidates); refs.to_csv(OUT / "cpht2_reference_review.csv", index=False)
    sensitivity, comparison = reference_sensitivity_and_conditions(physics, refs)
    sensitivity.to_csv(OUT / "cpht2_reference_sensitivity.csv", index=False)
    comparison.to_csv(OUT / "cpht2_reference_operating_comparison.csv", index=False)
    corrected_performance_outputs(physics).to_csv(OUT / "corrected_hx_performance_summary.csv", index=False)
    ts, metrics = validate_branch_15(physics); ts.to_csv(OUT / "pilot_branch_validation_timeseries.csv", index=False)
    metrics.to_csv(OUT / "pilot_branch_validation_metrics.csv", index=False)
    pd.DataFrame([
        {"order": 1, "node": "E103AB_IN", "tag": "1TI225.pv", "kind": "MEASURED", "direction": "forward"},
        {"order": 2, "node": "E103AB_OUT/E104_IN", "tag": "1TI136.pv", "kind": "MEASURED_CONTINUITY", "direction": "forward"},
        {"order": 3, "node": "E104_OUT", "tag": "1TI112.pv", "kind": "MEASURED", "direction": "forward"},
        {"order": 0, "node": "BRANCH_FLOW", "tag": "1FI015.pv", "kind": "SHARED_MEASURED", "direction": "forward"},
    ]).to_csv(OUT / "pilot_branch_topology.csv", index=False)
    evidence = maintenance_evidence(); evidence.to_csv(OUT / "maintenance_evidence.csv", index=False)
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
    axes[0].plot(ts.timestamp, ts.measured_e103_out_c, label="Measured E103 outlet"); axes[0].plot(ts.timestamp, ts.predicted_e103_out_c, label="Predicted", alpha=.8)
    axes[1].plot(ts.timestamp, ts.measured_e104_out_c, label="Measured E104 outlet"); axes[1].plot(ts.timestamp, ts.predicted_e104_out_c, label="Propagated prediction", alpha=.8)
    for ax in axes: ax.set_ylabel("Temperature (degC)"); ax.legend(); ax.grid(alpha=.2)
    axes[1].set_xlabel("Time (Asia/Bangkok)"); fig.suptitle("CPHT-2 branch-15 pilot chronological validation")
    fig.tight_layout(); fig.savefig(FIG / "pilot_branch_temperature_validation.png", dpi=140); plt.close(fig)
    summary = {"confirmed_clean_pilot_exists": False, "pilot_branch": "E103AB -> E104",
               "pilot_branch_status": "ENGINEERING_THRESHOLD_REQUIRED", "raw_data_modified": False,
               "replacement_tags_used": False, "interpolation_used": False}
    (OUT / "correction_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(metrics.to_string(index=False)); print(refs[["hx_id", "status", "valid_record_count", "candidate_count", "recommended_pilot"]].to_string(index=False))


if __name__ == "__main__":
    main()
