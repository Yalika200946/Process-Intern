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
            rec="INSUFFICIENT_VALID_COVERAGE"
        elif strongest is not None and strongest >= settings["strong_absolute_correlation"]:
            rec="CONDITION_STRATIFIED_EMPIRICAL_REFERENCE_REVIEW"
        else:
            rec="SIMPLE_EXPLICIT_WINDOW_MEDIAN_REVIEW"
        rows.append({"hx_id":hx_id,"ua_valid_coverage":coverage,"strongest_absolute_relationship":strongest,
                     "method_recommendation":rec,"approval_status":"REVIEW_ONLY_NOT_A_CLEAN_BASELINE",
                     "reason":"Recommendation reflects operating relationships only; maintenance evidence remains required."})
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


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--physics",type=Path,default=ROOT/"reports/tables/mvp_real_data/hx_physics_validation.csv");ap.add_argument("--states",type=Path,default=ROOT/"reports/tables/mvp_real_data/record_quality_states.csv");ap.add_argument("--mapping",type=Path,default=ROOT/"config/mvp_real_data_pilot.json");ap.add_argument("--settings",type=Path,default=ROOT/"config/mvp_relationship_review.json");args=ap.parse_args()
    physics=pd.read_csv(args.physics);physics["timestamp"]=pd.to_datetime(physics.timestamp,utc=True).dt.tz_convert("Asia/Bangkok");states=pd.read_csv(args.states);mapping=json.loads(args.mapping.read_text(encoding="utf-8"));settings=json.loads(args.settings.read_text(encoding="utf-8"));metadata=pd.read_csv(ROOT/"reports/tables/mvp_real_data/source_tag_metadata.csv")
    tables=ROOT/"reports/tables/mvp_real_data/coverage_completion";figures=ROOT/"reports/figures/mvp_real_data/coverage_completion";tables.mkdir(parents=True,exist_ok=True);figures.mkdir(parents=True,exist_ok=True)
    dq,warnings=data_quality_summary(states);dq.to_csv(tables/"data_quality_summary.csv",index=False);warnings.to_csv(tables/"warning_code_summary.csv",index=False)
    consolidated_mapping(mapping,metadata).to_csv(tables/"tag_mapping_availability.csv",index=False)
    temperature_validity(physics).to_csv(tables/"four_temperature_validity.csv",index=False)
    correlations=correlation_summary(physics,settings["minimum_paired_records"]);correlations.to_csv(tables/"relationship_correlations.csv",index=False)
    throughput,dist=throughput_summary(physics,settings);throughput.to_csv(tables/"ua_by_throughput_band.csv",index=False)
    method_recommendations(physics,correlations,settings).to_csv(tables/"baseline_method_review.csv",index=False)
    plot_hx_outputs(physics,figures);plot_throughput(dist,figures)
    print(f"Completed feasible B/C/C2 reporting for {physics.hx_id.nunique()} HX.")
    print("Qhot, closure, differential pressure, and configuration stratification remain unavailable.")


if __name__=="__main__":main()
