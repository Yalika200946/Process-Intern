"""Complete feasible B/C/C2 reporting without changing engineering calculations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def data_quality_summary(states: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    counts = states.groupby(["hx_id", "operating_state"]).size().unstack(fill_value=0)
    for state in ("SHUTDOWN", "STARTUP", "STEADY", "TRANSIENT", "INVALID_SENSOR", "UNAVAILABLE"):
        if state not in counts: counts[state] = 0
    summary = counts.reset_index()
    summary["total_records"] = summary[list(counts.columns)].sum(axis=1)
    for state in counts.columns:
        summary[f"{state.lower()}_pct"] = summary[state] / summary.total_records * 100
    warnings = states.assign(warning=states.quality_warning_code.fillna("").str.split("|"))
    warnings = warnings.explode("warning"); warnings = warnings[warnings.warning != ""]
    warning_summary = warnings.groupby(["hx_id", "warning"]).size().rename("record_count").reset_index()
    warning_summary["record_pct"] = warning_summary.record_count / warning_summary.hx_id.map(
        states.groupby("hx_id").size()) * 100
    return summary, warning_summary


def temporal_quality_audit(states: pd.DataFrame, long_gap_hours: float = 36.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Audit timestamps without filling gaps or removing invalid records."""
    rows, gaps = [], []
    work = states.copy(); work["timestamp"] = pd.to_datetime(work.timestamp)
    for hx_id, group in work.groupby("hx_id"):
        ordered = group.sort_values("timestamp")
        duplicate_count = int(ordered.timestamp.duplicated(keep=False).sum())
        delta = ordered.timestamp.diff().dt.total_seconds().div(3600)
        long = ordered.loc[delta > long_gap_hours, ["timestamp"]].copy()
        long["gap_hours"] = delta[delta > long_gap_hours].values
        long["hx_id"] = hx_id; gaps.append(long)
        flatline_count = int(ordered.quality_warning_code.fillna("").str.contains("SENSOR_FLATLINE").sum())
        rows.append({"hx_id": hx_id, "record_count": len(ordered),
                     "duplicate_timestamp_records": duplicate_count,
                     "median_sampling_interval_hours": float(delta.median()),
                     "long_gap_count": len(long), "flatline_record_count": flatline_count,
                     "long_gap_interpolation_used": False, "raw_records_removed": False})
    return pd.DataFrame(rows), pd.concat(gaps, ignore_index=True) if gaps else pd.DataFrame(
        columns=["timestamp", "gap_hours", "hx_id"])


def performance_summary(physics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for hx_id, group in physics.groupby("hx_id"):
        valid = group[group.operating_valid & group.ua_valid].copy()
        row = {"hx_id": hx_id, "total_records": len(group), "valid_records": len(valid),
               "valid_coverage_pct": len(valid) / len(group) * 100 if len(group) else 0,
               "output_status": "VALIDATED" if len(valid) >= 30 else "PARTIAL"}
        for field, prefix, unit in (("q_cold_value", "q_cold", "kW"),
                                    ("lmtd_value", "lmtd", "degC"),
                                    ("ua_w_m2_k", "u", "W/m2-K")):
            values = valid[field].dropna()
            row[f"median_{prefix}"] = values.median()
            row[f"iqr_{prefix}"] = values.quantile(.75) - values.quantile(.25)
            row[f"{prefix}_unit"] = unit
        rows.append(row)
    return pd.DataFrame(rows)


def consolidated_mapping(mapping: dict, metadata: pd.DataFrame) -> pd.DataFrame:
    units = dict(zip(metadata.source_tag.str.casefold(), metadata.source_unit))
    aliases = mapping["aliases"]
    rows = []
    for hx_id, hx in mapping["heat_exchangers"].items():
        if hx["status"] in {"UNAVAILABLE", "BLOCKED"}:
            rows.append({"hx_id": hx_id, "variable": "ALL_REQUIRED", "mapping_type": hx["status"],
                         "source_tags": "", "source_unit": "", "availability": hx["status"],
                         "reason": hx.get("blocked_reason", hx.get("unavailable_reason", ""))})
            continue
        for variable in ("cold_flow", "cold_in", "cold_out", "hot_in", "hot_out"):
            definition = hx[variable]
            if isinstance(definition, str):
                source = aliases.get(definition, definition); kind = "MEASURED"
                source_tags = source
            else:
                kind = "INFERRED" if definition["method"] == "row_max" else "CALCULATED"
                source_tags = ";".join(aliases.get(tag, tag) for tag in definition["tags"])
            source_units = ";".join(sorted({units.get(tag.casefold(), "UNKNOWN") for tag in source_tags.split(";")}))
            rows.append({"hx_id": hx_id, "variable": variable, "mapping_type": kind,
                         "source_tags": source_tags, "source_unit": source_units,
                         "availability": "AVAILABLE", "reason": "|".join(hx.get("mapping_warnings", []))})
    return pd.DataFrame(rows)


def temperature_validity(physics: pd.DataFrame) -> pd.DataFrame:
    p = physics.copy()
    p["cold_rise_valid"] = p.cold_out_c > p.cold_in_c
    p["hot_drop_valid"] = p.hot_in_c > p.hot_out_c
    p["terminal_1_valid"] = p.hot_in_c > p.cold_out_c
    p["terminal_2_valid"] = p.hot_out_c > p.cold_in_c
    fields = ["cold_rise_valid", "hot_drop_valid", "terminal_1_valid", "terminal_2_valid"]
    out = p.groupby("hx_id")[fields].agg(["sum", "mean"])
    out.columns = [f"{a}_{'count' if b == 'sum' else 'pct'}" for a, b in out.columns]
    for c in [x for x in out if x.endswith("_pct")]: out[c] *= 100
    return out.reset_index()


def correlation_summary(physics: pd.DataFrame, minimum: int) -> pd.DataFrame:
    pairs = [("q_cold_value","cold_flow_m3_h"),("q_cold_value","crude_temperature_rise_c"),
             ("ua_w_m2_k","cold_flow_m3_h"),("ua_w_m2_k","lmtd_value"),
             ("ua_w_m2_k","hot_in_c"),("ua_w_m2_k","sg_15_6c")]
    rows = []
    for hx_id, g in physics.groupby("hx_id"):
        valid = g[g.operating_valid & g.ua_valid].copy()
        valid["crude_temperature_rise_c"] = valid.cold_out_c - valid.cold_in_c
        for y, x in pairs:
            pair = valid[[x, y]].dropna()
            rows.append({"hx_id": hx_id, "x_variable": x, "y_variable": y,
                         "paired_records": len(pair),
                         "pearson": pair[x].corr(pair[y], method="pearson") if len(pair) >= minimum else None,
                         "spearman": pair[x].corr(pair[y], method="spearman") if len(pair) >= minimum else None,
                         "status": "VALID" if len(pair) >= minimum else "INSUFFICIENT_POINTS"})
    return pd.DataFrame(rows)


def throughput_summary(physics: pd.DataFrame, settings: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames, rows = [], []
    for hx_id, g in physics.groupby("hx_id"):
        valid = g[g.operating_valid & g.ua_valid & g.ua_w_m2_k.notna()].copy()
        if valid.cold_flow_m3_h.nunique() < 3: continue
        try:
            valid["throughput_band"] = pd.qcut(valid.cold_flow_m3_h,
                                                settings["throughput_band_quantiles"],
                                                labels=settings["throughput_band_labels"], duplicates="drop")
        except ValueError:
            continue
        frames.append(valid)
        for band, b in valid.groupby("throughput_band", observed=True):
            rows.append({"hx_id": hx_id, "throughput_band": str(band), "record_count": len(b),
                         "flow_min_m3_h": b.cold_flow_m3_h.min(), "flow_max_m3_h": b.cold_flow_m3_h.max(),
                         "median_ua_w_m2_k": b.ua_w_m2_k.median(), "ua_iqr_w_m2_k": b.ua_w_m2_k.quantile(.75)-b.ua_w_m2_k.quantile(.25)})
    return pd.DataFrame(rows), pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def method_recommendations(physics: pd.DataFrame, correlations: pd.DataFrame, settings: dict) -> pd.DataFrame:
    rows=[]
    for hx_id,g in physics.groupby("hx_id"):
        coverage=float(g.ua_valid.mean()); c=correlations[(correlations.hx_id==hx_id)&(correlations.y_variable=="ua_w_m2_k")]
        strongest=float(c[["pearson","spearman"]].abs().max().max()) if c[["pearson","spearman"]].notna().any().any() else None
        if coverage < settings["minimum_valid_coverage_for_method_review"]:
            rec="INSUFFICIENT_DATA"
        elif strongest is not None and strongest >= settings["strong_absolute_correlation"]:
            rec="OPERATING_ADJUSTED_REFERENCE"
        elif strongest is not None and strongest >= 0.30:
            rec="STRATIFIED_REFERENCE"
        else:
            rec="FIXED_EMPIRICAL_REFERENCE"
        rows.append({"hx_id":hx_id,"ua_valid_coverage":coverage,"strongest_absolute_relationship":strongest,
                     "method_recommendation":rec,"approval_status":"REVIEW_ONLY_NOT_A_CLEAN_BASELINE",
                     "reason":"Recommendation reflects operating relationships only; maintenance evidence remains required."})
    return pd.DataFrame(rows)


def operating_model_screening(physics: pd.DataFrame, minimum: int = 60) -> pd.DataFrame:
    """Chronological Ridge screening; descriptive only, never a clean model."""
    rows=[]
    features=["cold_flow_m3_h","lmtd_value","cold_in_c","hot_in_c","sg_15_6c"]
    for hx_id,g in physics.groupby("hx_id"):
        valid=g[g.operating_valid & g.ua_valid].sort_values("timestamp").copy()
        valid["time_days"]=(valid.timestamp-valid.timestamp.min()).dt.total_seconds()/86400
        cols=features+["time_days"]
        frame=valid[cols+["ua_w_m2_k"]].dropna()
        if len(frame)<minimum:
            rows.append({"hx_id":hx_id,"status":"PARTIAL","valid_sample_count":len(frame),
                         "model":"RIDGE_SCREENING","reason":"INSUFFICIENT_COMPLETE_CASES"});continue
        split=max(int(len(frame)*.8),1);train,test=frame.iloc[:split],frame.iloc[split:]
        mean=train[cols].mean();std=train[cols].std().replace(0,1)
        x=(train[cols]-mean)/std;y=train.ua_w_m2_k.to_numpy();design=np.c_[np.ones(len(x)),x.to_numpy()]
        penalty=np.eye(design.shape[1]);penalty[0,0]=0
        beta=np.linalg.solve(design.T@design+penalty,design.T@y)
        xt=(test[cols]-mean)/std;pred=np.c_[np.ones(len(xt)),xt.to_numpy()]@beta
        rmse=float(np.sqrt(np.mean((test.ua_w_m2_k.to_numpy()-pred)**2))) if len(test) else np.nan
        scale=float(test.ua_w_m2_k.std()) if len(test)>1 else np.nan
        row={"hx_id":hx_id,"status":"EXPLORATORY","valid_sample_count":len(frame),
             "train_count":len(train),"test_count":len(test),"model":"RIDGE_SCREENING",
             "holdout_rmse_w_m2_k":rmse,"holdout_rmse_over_test_std":rmse/scale if scale else np.nan,
             "design_condition_number":float(np.linalg.cond(design)),
             "multicollinearity_warning":bool(np.linalg.cond(design)>30),
             "causal_interpretation_allowed":False}
        row.update({f"coefficient_{name}":float(beta[i+1]) for i,name in enumerate(cols)})
        rows.append(row)
    return pd.DataFrame(rows)


def _shade_invalid(ax, g):
    bad = ~g.operating_valid
    starts = bad & ~bad.shift(1, fill_value=False); ends = bad & ~bad.shift(-1, fill_value=False)
    for start, end in zip(g.loc[starts,"timestamp"], g.loc[ends,"timestamp"]):
        ax.axvspan(start, end + pd.Timedelta(days=1), color="#d73027", alpha=.09)


def plot_hx_outputs(physics: pd.DataFrame, output: Path):
    rel_dir=output/"relationships"; aligned_dir=output/"aligned_timelines"; rel_dir.mkdir(parents=True,exist_ok=True);aligned_dir.mkdir(parents=True,exist_ok=True)
    pairs=[("cold_flow_m3_h","q_cold_value","Crude flow (m³/h)","Qcold (kW)"),
           ("crude_temperature_rise_c","q_cold_value","Crude ΔT (°C)","Qcold (kW)"),
           ("cold_flow_m3_h","ua_w_m2_k","Crude flow (m³/h)","U (W/m²·K)"),
           ("lmtd_value","ua_w_m2_k","LMTD (°C)","U (W/m²·K)"),
           ("hot_in_c","ua_w_m2_k","Hot-inlet temperature (°C)","U (W/m²·K)"),
           ("sg_15_6c","ua_w_m2_k","Crude SG at 15.6°C (-)","U (W/m²·K)")]
    for hx_id,g in physics.groupby("hx_id"):
        g=g.sort_values("timestamp").copy();g["crude_temperature_rise_c"]=g.cold_out_c-g.cold_in_c;valid=g[g.operating_valid & g.ua_valid]
        fig,axes=plt.subplots(2,3,figsize=(16,9))
        for ax,(x,y,xlabel,ylabel) in zip(axes.ravel(),pairs):
            pair=valid[[x,y]].dropna();ax.scatter(pair[x],pair[y],s=9,alpha=.4);ax.set_xlabel(xlabel);ax.set_ylabel(ylabel);ax.set_title(f"n={len(pair):,}; excluded={len(g)-len(pair):,}");ax.grid(alpha=.2)
        fig.suptitle(f"{hx_id} — operating-relationship screening (valid steady records only)");fig.tight_layout();fig.savefig(rel_dir/f"{hx_id}_relationships.png",dpi=140,bbox_inches="tight");plt.close(fig)
        fig,axes=plt.subplots(4,1,figsize=(16,11),sharex=True)
        for ax,col,label in zip(axes,["q_cold_value","lmtd_value","ua_w_m2_k","cold_flow_m3_h"],["Qcold (kW)","LMTD (°C)","U (W/m²·K)","Crude flow (m³/h)"]):
            ax.plot(g.timestamp,g[col],lw=.7);_shade_invalid(ax,g);ax.set_ylabel(label);ax.grid(alpha=.2)
        axes[0].set_title(f"{hx_id} — aligned physics timeline (red shading = invalid/non-operating)");axes[-1].set_xlabel("Time (Asia/Bangkok)");fig.tight_layout();fig.savefig(aligned_dir/f"{hx_id}_aligned_timeline.png",dpi=140,bbox_inches="tight");plt.close(fig)


def plot_throughput(distributions: pd.DataFrame, output: Path):
    if distributions.empty:return
    hx_ids=list(distributions.hx_id.unique());fig,axes=plt.subplots(5,3,figsize=(15,18));
    for ax,hx in zip(axes.ravel(),hx_ids):
        g=distributions[distributions.hx_id==hx];groups=[g.loc[g.throughput_band==b,"ua_w_m2_k"].dropna() for b in ["LOW","MEDIUM","HIGH"]]
        ax.boxplot(groups,tick_labels=["LOW","MEDIUM","HIGH"],showfliers=False);ax.set_title(hx);ax.set_ylabel("U (W/m²·K)")
    for ax in axes.ravel()[len(hx_ids):]:ax.set_visible(False)
    fig.suptitle("UA stratified by per-HX crude-throughput quantile band");fig.tight_layout();fig.savefig(output/"ua_by_throughput_band.png",dpi=140,bbox_inches="tight");plt.close(fig)


def plot_performance_comparison(summary: pd.DataFrame, output: Path):
    fig, axes = plt.subplots(1, 3, figsize=(17, 5))
    for ax, value, spread, ylabel in zip(
        axes, ["median_q_cold", "median_lmtd", "median_u"],
        ["iqr_q_cold", "iqr_lmtd", "iqr_u"],
        ["Qcold (kW)", "LMTD (degC)", "U (W/m2-K)"],
    ):
        ax.errorbar(summary.hx_id, summary[value], yerr=summary[spread] / 2, fmt="o", capsize=3)
        ax.set_ylabel(ylabel); ax.tick_params(axis="x", rotation=65); ax.grid(alpha=.2)
    fig.suptitle("HX performance comparison: median and half-IQR (valid steady records)")
    fig.tight_layout(); fig.savefig(output / "hx_performance_median_iqr.png", dpi=140, bbox_inches="tight"); plt.close(fig)


def plot_temperature_validity(summary:pd.DataFrame,output:Path):
    columns=[c for c in summary if c.endswith("_pct")];data=summary.set_index("hx_id")[columns]
    fig,ax=plt.subplots(figsize=(11,6));im=ax.imshow(data,aspect="auto",vmin=0,vmax=100,cmap="RdYlGn");ax.set_yticks(range(len(data)),data.index);ax.set_xticks(range(len(columns)),[c.replace("_pct","") for c in columns],rotation=25,ha="right");ax.set_title("Four-temperature relationship validity coverage");fig.colorbar(im,ax=ax,label="Valid records (%)");fig.tight_layout();fig.savefig(output/"four_temperature_validity.png",dpi=140);plt.close(fig)


def plot_operating_adjusted_residuals(physics:pd.DataFrame,output:Path):
    directory=output/"operating_adjusted_residuals";directory.mkdir(parents=True,exist_ok=True);features=["cold_flow_m3_h","lmtd_value","cold_in_c","hot_in_c","sg_15_6c"]
    for hx_id,g in physics.groupby("hx_id"):
        frame=g[g.operating_valid & g.ua_valid][["timestamp","ua_w_m2_k",*features]].dropna().sort_values("timestamp")
        if len(frame)<60:continue
        x=frame[features];mean=x.mean();std=x.std().replace(0,1);design=np.c_[np.ones(len(x)),((x-mean)/std).to_numpy()];pen=np.eye(design.shape[1]);pen[0,0]=0;beta=np.linalg.solve(design.T@design+pen,design.T@frame.ua_w_m2_k.to_numpy());residual=frame.ua_w_m2_k.to_numpy()-design@beta
        fig,ax=plt.subplots(figsize=(14,4));ax.plot(frame.timestamp,residual,lw=.7);ax.axhline(0,color="black",ls="--");ax.set(xlabel="Time (Asia/Bangkok)",ylabel="U residual (W/m2-K)",title=f"{hx_id} - exploratory operating-adjusted U residual");ax.grid(alpha=.2);fig.tight_layout();fig.savefig(directory/f"{hx_id}_ua_residual.png",dpi=140);plt.close(fig)


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--physics",type=Path,default=ROOT/"reports/tables/mvp_real_data/hx_physics_validation.csv");ap.add_argument("--states",type=Path,default=ROOT/"reports/tables/mvp_real_data/record_quality_states.csv");ap.add_argument("--mapping",type=Path,default=ROOT/"config/mvp_real_data_pilot.json");ap.add_argument("--settings",type=Path,default=ROOT/"config/mvp_relationship_review.json");args=ap.parse_args()
    physics=pd.read_csv(args.physics);physics["timestamp"]=pd.to_datetime(physics.timestamp,utc=True).dt.tz_convert("Asia/Bangkok");states=pd.read_csv(args.states);states["timestamp"]=pd.to_datetime(states.timestamp,utc=True).dt.tz_convert("Asia/Bangkok");mapping=json.loads(args.mapping.read_text(encoding="utf-8"));settings=json.loads(args.settings.read_text(encoding="utf-8"));metadata=pd.read_csv(ROOT/"reports/tables/mvp_real_data/source_tag_metadata.csv")
    tables=ROOT/"reports/tables/mvp_real_data/coverage_completion";figures=ROOT/"reports/figures/mvp_real_data/coverage_completion";tables.mkdir(parents=True,exist_ok=True);figures.mkdir(parents=True,exist_ok=True)
    dq,warnings=data_quality_summary(states);dq.to_csv(tables/"data_quality_summary.csv",index=False);warnings.to_csv(tables/"warning_code_summary.csv",index=False)
    consolidated_mapping(mapping,metadata).to_csv(tables/"tag_mapping_availability.csv",index=False)
    temporal, gaps = temporal_quality_audit(states, mapping["rules"]["long_gap_hours"]); temporal.to_csv(tables/"temporal_quality_summary.csv",index=False); gaps.to_csv(tables/"long_gap_records.csv",index=False)
    temp_validity=temperature_validity(physics);temp_validity.to_csv(tables/"four_temperature_validity.csv",index=False)
    correlations=correlation_summary(physics,settings["minimum_paired_records"]);correlations.to_csv(tables/"relationship_correlations.csv",index=False)
    throughput,dist=throughput_summary(physics,settings);throughput.to_csv(tables/"ua_by_throughput_band.csv",index=False)
    method_recommendations(physics,correlations,settings).to_csv(tables/"baseline_method_review.csv",index=False)
    operating_model_screening(physics).to_csv(tables/"operating_adjusted_model_screening.csv",index=False)
    perf=performance_summary(physics);perf.to_csv(tables/"hx_performance_summary.csv",index=False)
    plot_hx_outputs(physics,figures);plot_throughput(dist,figures);plot_performance_comparison(perf,figures);plot_temperature_validity(temp_validity,figures);plot_operating_adjusted_residuals(physics,figures)
    print(f"Completed feasible B/C/C2 reporting for {physics.hx_id.nunique()} HX.")
    print("Qhot, closure, differential pressure, and configuration stratification remain unavailable.")


if __name__=="__main__":main()
