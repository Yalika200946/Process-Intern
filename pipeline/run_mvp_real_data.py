"""Run only MVP Data Readiness and HX Physics Validation on real plant data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.calculations.heat_duty import calculate_cold_side_heat_duty, calculate_mass_flow
from src.calculations.heat_transfer import calculate_lmtd, calculate_ua
from src.domain.crude_properties import calculate_crude_cp, calculate_crude_density
from src.validation.real_data import (
    candidate_stable_periods, classify_hx_records, load_dcs_matrix, load_pilot_config,
)


def _result_fields(result, prefix):
    quality = result.quality or {}
    warnings = list(result.warnings or ())
    valid = bool(quality.get("is_valid", result.value is not None))
    return {f"{prefix}_value": result.value, f"{prefix}_unit": result.unit,
            f"{prefix}_basis": result.basis, f"{prefix}_data_kind": result.data_kind,
            f"{prefix}_confidence": result.confidence, f"{prefix}_approval_status": result.approval_status,
            f"{prefix}_assumptions": "|".join(warnings),
            f"{prefix}_valid": valid,
            f"{prefix}_warning_code": quality.get("warning_code", "|".join(warnings)),
            f"{prefix}_reason": quality.get("reason", " ".join(warnings))}


def _load_crude_properties(config):
    crude = pd.read_csv(config["dataset"]["crude_properties_path"])
    crude["crude_date"] = pd.to_datetime(crude["Date"], errors="coerce").dt.date
    return crude[["crude_date", "SG_15_6C"]].drop_duplicates("crude_date", keep="last")


def calculate_physics(states, hx, config, crude):
    work = states.copy()
    work["crude_date"] = work.timestamp.dt.tz_localize(None).dt.date
    work = work.merge(crude, on="crude_date", how="left")
    rows = []
    factor = float(config["rules"]["lmtd_correction_factor"])
    area = float(hx["area_m2"])
    for row in work.itertuples(index=False):
        record = {"timestamp": row.timestamp, "hx_id": row.hx_id,
                  "operating_state": row.operating_state,
                  "operating_valid": bool(row.operating_valid),
                  "data_available": bool(row.data_available),
                  "quality_warning_code": row.quality_warning_code,
                  "quality_reason": row.quality_reason,
                  "data_kind": row.data_kind,
                  "cold_flow_m3_h": row.cold_flow, "cold_in_c": row.cold_in,
                  "cold_out_c": row.cold_out, "hot_in_c": row.hot_in,
                  "hot_out_c": row.hot_out, "hot_in_data_kind": row.hot_in_data_kind,
                  "cold_flow_data_kind": row.cold_flow_data_kind,
                  "sg_15_6c": row.SG_15_6C, "correction_factor": factor,
                  "correction_factor_status": config["rules"]["lmtd_correction_factor_status"],
                  "area_m2": area, "q_hot_status": "UNAVAILABLE",
                  "q_hot_warning_code": "MISSING_APPROVED_HOT_STREAM_PROPERTIES",
                  "delta_p_status": "UNAVAILABLE",
                  "delta_p_warning_code": "NO_CONFIRMED_HX_INLET_OUTLET_PRESSURE_PAIR"}
        record.update({"cold_delta_t_c": row.cold_out-row.cold_in,
                       "hot_delta_t_c": row.hot_in-row.hot_out,
                       "terminal_delta_t_1_c": row.hot_in-row.cold_out,
                       "terminal_delta_t_2_c": row.hot_out-row.cold_in,
                       "four_temperature_valid": bool(row.hot_in>row.hot_out and row.cold_out>row.cold_in and row.hot_in>row.cold_out and row.hot_out>row.cold_in)})
        if not row.operating_valid or not np.isfinite(row.SG_15_6C):
            reason = "Record is not operating-valid." if not row.operating_valid else "Crude SG is unavailable for this date."
            code = "INVALID_OPERATING_RECORD" if not row.operating_valid else "MISSING_CRUDE_PROPERTY"
            for name, unit in (("mass_flow", "kg/s"), ("q_cold", "kW"),
                               ("lmtd", "degC"), ("ua", "kW/K")):
                record.update({f"{name}_value": None, f"{name}_unit": unit,
                               f"{name}_basis": "canonical calculation unavailable",
                               f"{name}_data_kind": "UNAVAILABLE", f"{name}_confidence": "NONE",
                               f"{name}_approval_status": "UNAVAILABLE", f"{name}_assumptions": "",
                               f"{name}_valid": False, f"{name}_warning_code": code,
                               f"{name}_reason": reason})
            record.update({"cp_kj_kg_k": None, "density_kg_m3": None,
                           "ua_w_m2_k": None, "ua_valid": False})
            rows.append(record); continue
        avg_temp = (row.cold_in + row.cold_out) / 2
        try:
            cp = calculate_crude_cp(avg_temp, row.SG_15_6C)
            density = calculate_crude_density(avg_temp, row.SG_15_6C)
            mass = calculate_mass_flow(row.cold_flow, density.value)
            duty = calculate_cold_side_heat_duty(row.cold_flow, density.value, cp.value,
                                                  row.cold_in, row.cold_out)
            lmtd = calculate_lmtd(row.hot_in - row.cold_out, row.hot_out - row.cold_in,
                                  equal_tolerance_c=0.1)
            ua = calculate_ua(duty.value, lmtd.value, factor)
            record.update(_result_fields(mass, "mass_flow")); record.update(_result_fields(duty, "q_cold"))
            record.update(_result_fields(lmtd, "lmtd")); record.update(_result_fields(ua, "ua"))
            record.update({"cp_kj_kg_k": cp.value, "density_kg_m3": density.value,
                           "ua_w_m2_k": ua.value * 1000 / area,
                           "ua_valid": bool(record["ua_valid"] and ua.value > 0)})
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            for name, unit in (("mass_flow", "kg/s"), ("q_cold", "kW"),
                               ("lmtd", "degC"), ("ua", "kW/K")):
                record.update({f"{name}_value": None, f"{name}_unit": unit,
                               f"{name}_basis": "canonical calculation invalid",
                               f"{name}_data_kind": "UNAVAILABLE", f"{name}_confidence": "NONE",
                               f"{name}_approval_status": "UNAVAILABLE", f"{name}_assumptions": "",
                               f"{name}_valid": False, f"{name}_warning_code": "CANONICAL_CALCULATION_INVALID",
                               f"{name}_reason": str(exc)})
            record.update({"cp_kj_kg_k": None, "density_kg_m3": None,
                           "ua_w_m2_k": None, "ua_valid": False})
        rows.append(record)
    return pd.DataFrame(rows)


def _save(fig, path):
    fig.tight_layout(); fig.savefig(path, dpi=140, bbox_inches="tight"); plt.close(fig)


def create_plots(raw, metadata, states, physics, config, fig_dir):
    fig_dir.mkdir(parents=True, exist_ok=True)
    hx_order = list(config["heat_exchangers"])
    display = states.copy()
    display["availability_kind"] = 2
    display.loc[~display.data_available, "availability_kind"] = 1
    display.loc[display.operating_state == "UNAVAILABLE", "availability_kind"] = 0
    display.loc[display.hot_in_data_kind == "INFERRED", "availability_kind"] = 3
    display.loc[display.cold_flow_data_kind == "CALCULATED", "availability_kind"] = 4
    display.loc[display.operating_state == "INVALID_SENSOR", "availability_kind"] = 5
    availability = display.pivot(index="hx_id", columns="timestamp", values="availability_kind").reindex(hx_order)
    fig, ax = plt.subplots(figsize=(16, 6)); im=ax.imshow(availability, aspect="auto", interpolation="nearest", cmap="tab10",vmin=0,vmax=5)
    ax.set_yticks(range(len(availability))); ax.set_yticklabels(availability.index); ax.set_xlabel("Time (Asia/Bangkok)"); ax.set_title("Required-data availability and provenance")
    c=fig.colorbar(im,ax=ax);c.set_ticks(range(6));c.set_ticklabels(["Unavailable","Missing","Measured","Inferred","Calculated","Invalid"])
    _save(fig, fig_dir / "01_data_availability_heatmap.png")

    required = ["cold_flow", "cold_in", "cold_out", "hot_in", "hot_out"]
    miss = states.groupby("hx_id")[required].agg(lambda x: x.isna().mean() * 100).reindex(hx_order)
    fig, ax = plt.subplots(figsize=(14, 6)); miss.plot.bar(ax=ax); ax.set_ylabel("Missing records (%)"); ax.set_xlabel("HX"); ax.set_title("Missing percentage by required variable"); ax.legend(ncol=5, fontsize=8)
    _save(fig, fig_dir / "02_missing_percentage.png")

    delta_h = raw.timestamp.sort_values().diff().dt.total_seconds().div(3600).dropna()
    fig, ax = plt.subplots(figsize=(9, 5)); ax.hist(delta_h, bins=min(30, max(1, delta_h.nunique() * 3))); ax.set_xlabel("Sampling interval (hours)"); ax.set_ylabel("Count"); ax.set_title("Sampling-interval distribution")
    _save(fig, fig_dir / "03_sampling_interval.png")

    state_code = {"UNAVAILABLE":0,"INVALID_SENSOR":1,"SHUTDOWN":2,"STARTUP":3,"TRANSIENT":4,"STEADY":5}
    timeline = states.assign(code=states.operating_state.map(state_code)).pivot(index="hx_id",columns="timestamp",values="code").reindex(hx_order)
    fig, ax = plt.subplots(figsize=(16, 6)); im=ax.imshow(timeline, aspect="auto", interpolation="nearest", cmap="viridis",vmin=0,vmax=5); ax.set_yticks(range(len(timeline)));ax.set_yticklabels(timeline.index);ax.set_xlabel("Time (Asia/Bangkok)");ax.set_title("Operating-state timeline"); c=fig.colorbar(im,ax=ax);c.set_ticks(range(6));c.set_ticklabels(list(state_code))
    _save(fig, fig_dir / "05_operating_state_timeline.png")

    valid_physics = physics[physics.hx_id.notna()]
    coverage = valid_physics.groupby("hx_id")[["operating_valid","mass_flow_valid","q_cold_valid","lmtd_valid","ua_valid"]].mean().mul(100).reindex(hx_order)
    fig, ax=plt.subplots(figsize=(14,6));coverage.plot.bar(ax=ax);ax.set_ylabel("Valid records (%)");ax.set_xlabel("HX");ax.set_title("Calculation-validity coverage");ax.legend(fontsize=8)
    _save(fig, fig_dir / "10_calculation_validity_coverage.png")

    for hx_id, g in valid_physics.groupby("hx_id"):
        if g[["cold_flow_m3_h","cold_in_c","cold_out_c","hot_in_c","hot_out_c"]].notna().sum().sum() == 0:
            continue
        hdir=fig_dir/hx_id;hdir.mkdir(exist_ok=True)
        bad=~g.operating_valid
        fig,axs=plt.subplots(2,1,figsize=(15,8),sharex=True)
        for c,label,color in [("cold_in_c","Cold in (measured)","#1f77b4"),("cold_out_c","Cold out (measured)","#17becf"),("hot_in_c",f"Hot in ({g.hot_in_data_kind.iloc[0].lower()})","#d62728"),("hot_out_c","Hot out (measured)","#ff7f0e")]: axs[0].plot(g.timestamp,g[c],label=label,lw=.8,color=color)
        axs[0].scatter(g.loc[bad,"timestamp"],g.loc[bad,"cold_in_c"],s=7,color="black",label="Invalid/non-operating");axs[0].set_ylabel("Temperature (°C)");axs[0].legend(ncol=3,fontsize=7);axs[0].set_title(f"{hx_id} — four-temperature profile")
        flow_kind=g.cold_flow_data_kind.iloc[0].lower()
        axs[1].plot(g.timestamp,g.cold_flow_m3_h,color="#2ca25f",lw=.8,label=f"Crude flow ({flow_kind})");axs[1].scatter(g.loc[bad,"timestamp"],g.loc[bad,"cold_flow_m3_h"],s=7,color="black");axs[1].set_ylabel("Crude flow (m³/h)");axs[1].set_xlabel("Time (Asia/Bangkok)");axs[1].legend(fontsize=7)
        _save(fig,hdir/"01_raw_temperatures_flow.png")
        for idx,(column,ylabel,title) in enumerate([("q_cold_value","Crude-side duty (kW)","Crude-side heat duty"),("lmtd_value","LMTD (°C)","LMTD"),("ua_w_m2_k","U (W/m²·K)","Overall heat-transfer coefficient")],2):
            if not g[column].notna().any(): continue
            fig,ax=plt.subplots(figsize=(15,4));ax.plot(g.timestamp,g[column],lw=.8);ax.scatter(g.loc[~g[f'{column.split("_value")[0]}_valid'] if column.endswith('_value') else ~g.ua_valid,"timestamp"],g.loc[~g[f'{column.split("_value")[0]}_valid'] if column.endswith('_value') else ~g.ua_valid,column],s=8,color="black",label="Invalid/non-operating");ax.set_ylabel(ylabel);ax.set_xlabel("Time (Asia/Bangkok)");ax.set_title(f"{hx_id} — {title}");ax.legend(fontsize=7)
            _save(fig,hdir/f"0{idx}_{column}.png")
        vg=g[g.ua_valid & g.ua_w_m2_k.notna()]
        if len(vg):
            fig,ax=plt.subplots(figsize=(7,5));ax.scatter(vg.cold_flow_m3_h,vg.ua_w_m2_k,s=9,alpha=.5);ax.set_xlabel("Crude flow (m³/h)");ax.set_ylabel("U (W/m²·K)");ax.set_title(f"{hx_id} — U versus crude flow")
            _save(fig,hdir/"05_ua_vs_crude_flow.png")


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--config",default=str(ROOT/"config"/"mvp_real_data_pilot.json"));args=parser.parse_args()
    config=load_pilot_config(args.config);raw,metadata=load_dcs_matrix(config);crude=_load_crude_properties(config)
    states_parts=[];physics_parts=[]
    for hx_id,hx in config["heat_exchangers"].items():
        states=classify_hx_records(raw,hx_id,hx,config);states_parts.append(states)
        if hx["status"] not in {"UNAVAILABLE","BLOCKED"}: physics_parts.append(calculate_physics(states,hx,config,crude))
    states=pd.concat(states_parts,ignore_index=True);physics=pd.concat(physics_parts,ignore_index=True)
    table_dir=ROOT/"reports"/"tables"/"mvp_real_data";fig_dir=ROOT/"reports"/"figures"/"mvp_real_data";table_dir.mkdir(parents=True,exist_ok=True)
    states.to_csv(table_dir/"record_quality_states.csv",index=False);physics.to_csv(table_dir/"hx_physics_validation.csv",index=False)
    candidates=candidate_stable_periods(physics,config["rules"]);candidates.to_csv(table_dir/"candidate_stable_periods.csv",index=False)
    coverage=physics.groupby("hx_id")[["operating_valid","q_cold_valid","lmtd_valid","ua_valid"]].mean().mul(100);coverage.to_csv(table_dir/"calculation_coverage.csv")
    metadata.to_csv(table_dir/"source_tag_metadata.csv",index=False)
    unavailable=pd.DataFrame([{"hx_id":k,"status":v["status"],"reason":v.get("blocked_reason",v.get("unavailable_reason","")),"q_hot":"MISSING_APPROVED_HOT_STREAM_PROPERTIES","delta_p":"NO_CONFIRMED_HX_INLET_OUTLET_PRESSURE_PAIR"} for k,v in config["heat_exchangers"].items()])
    unavailable.to_csv(table_dir/"availability_register.csv",index=False)
    create_plots(raw,metadata,states,physics,config,fig_dir)
    summary={"dataset_start":str(raw.timestamp.min()),"dataset_end":str(raw.timestamp.max()),"rows":len(raw),"hx_configured":len(config["heat_exchangers"]),"candidate_windows":len(candidates),"scope":"DATA_READINESS_AND_HX_PHYSICS_ONLY"}
    (table_dir/"run_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2));print(f"Runtime tables: {table_dir}");print(f"Runtime figures: {fig_dir}")

if __name__ == "__main__": main()
