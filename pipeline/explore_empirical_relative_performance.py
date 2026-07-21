"""Exploratory relative performance against empirical high-performance periods.

This module deliberately does not emit canonical clean-baseline, fouling, or
CIT fields.  All records are operating-valid and all reference semantics are
explicitly provisional and non-clean.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STATUS = "EMPIRICAL_HIGH_PERFORMANCE_REFERENCE"
MIN_REFERENCE_RECORDS = 5
INTERPRETATION = ("Relative thermal performance against a high-performance historical period, "
                  "not a confirmed clean-state fouling measurement.")


def calculate_relative_performance(physics: pd.DataFrame, spec: dict) -> tuple[pd.DataFrame, dict]:
    hx = physics[(physics.hx_id == spec["hx_id"]) & physics.operating_valid & physics.ua_valid].copy()
    hx = hx[np.isfinite(hx.ua_value) & (hx.ua_value > 0)].sort_values("timestamp")
    start = pd.Timestamp(spec["start"], tz="Asia/Bangkok")
    end = pd.Timestamp(spec["end"], tz="Asia/Bangkok")
    reference = hx[(hx.timestamp >= start) & (hx.timestamp <= end)]
    if len(reference) < MIN_REFERENCE_RECORDS:
        summary = {
            "hx_id": spec["hx_id"],
            "empirical_reference_start": start,
            "empirical_reference_end": end,
            "empirical_reference_status": STATUS,
            "empirical_reference_valid_records": int(len(reference)),
            "empirical_reference_confidence": "INSUFFICIENT",
            "empirical_reference_warning_code": "INSUFFICIENT_REFERENCE_DATA",
            "status": "INSUFFICIENT_REFERENCE_DATA",
            "cleaning_event_confirmed": False,
            "clean_condition_confirmed": False,
            "impact_status": "BLOCKED_BY_REFERENCE_SEMANTICS",
        }
        return hx.iloc[0:0].copy(), summary
    reference_ua = float(reference.ua_value.median())
    reference_u = float(reference.ua_w_m2_k.median())
    hx["reference_ua_empirical"] = reference_ua
    hx["reference_ua_empirical_unit"] = "kW/K"
    hx["reference_u_w_m2_k"] = reference_u
    hx["relative_ua_empirical"] = hx.ua_value / reference_ua
    hx["relative_performance_loss"] = 1.0 - hx.relative_ua_empirical
    hx["empirical_reference_warning_code"] = np.where(
        hx.relative_performance_loss < 0, "ABOVE_EMPIRICAL_REFERENCE", ""
    )
    hx["empirical_reference_status"] = STATUS
    hx["empirical_reference_start"] = start
    hx["empirical_reference_end"] = end
    hx["empirical_reference_valid_records"] = int(len(reference))
    hx["empirical_reference_confidence"] = "MEDIUM_DESCRIPTIVE_ONLY"
    hx["source_reference_status"] = spec["reference_status"]
    hx["cleaning_event_confirmed"] = False
    hx["clean_condition_confirmed"] = False
    hx["interpretation"] = INTERPRETATION
    hx["impact_status"] = "BLOCKED_BY_REFERENCE_SEMANTICS"
    hx["network_effects_included"] = False
    summary = {"hx_id": spec["hx_id"], "empirical_reference_start": start,
               "empirical_reference_end": end, "empirical_reference_status": STATUS,
               "source_reference_status": spec["reference_status"],
               "empirical_reference_valid_records": int(len(reference)),
               "reference_ua_empirical": reference_ua,
               "reference_ua_empirical_unit": "kW/K", "reference_u_w_m2_k": reference_u,
               "empirical_reference_confidence": "MEDIUM_DESCRIPTIVE_ONLY",
               "empirical_reference_warning_code": "",
               "relative_ua_empirical_min": float(hx.relative_ua_empirical.min()),
               "relative_ua_empirical_max": float(hx.relative_ua_empirical.max()),
               "relative_performance_loss_min": float(hx.relative_performance_loss.min()),
               "relative_performance_loss_max": float(hx.relative_performance_loss.max()),
               "records_above_reference_pct": float((hx.relative_ua_empirical > 1).mean() * 100),
               "valid_record_count": int(len(hx)), "cleaning_event_confirmed": False,
               "clean_condition_confirmed": False, "interpretation": INTERPRETATION,
               "impact_status": "BLOCKED_BY_REFERENCE_SEMANTICS",
               "network_effects_included": False}
    return hx, summary


def relationship_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    candidates = {
        "cold_flow_m3_h": frame.cold_flow_m3_h,
        "lmtd_value": frame.lmtd_value,
        "hot_in_c": frame.hot_in_c,
        "time_days": (frame.timestamp - frame.timestamp.min()).dt.total_seconds() / 86400.0,
    }
    for name, values in candidates.items():
        pair=pd.DataFrame({"x":values,"relative_performance_loss":frame.relative_performance_loss}).dropna()
        rows.append({"hx_id":frame.hx_id.iloc[0],"x_variable":name,"valid_sample_count":len(pair),
                     "pearson":pair.x.corr(pair.relative_performance_loss,method="pearson"),
                     "spearman":pair.x.corr(pair.relative_performance_loss,method="spearman"),
                     "interpretation":"Association only; a downward trend is not automatically fouling."})
    return pd.DataFrame(rows)


def throughput_distribution(frame: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    out=frame.copy();out["throughput_band"]=pd.qcut(out.cold_flow_m3_h,[0,.33,.67,1],labels=["LOW","MEDIUM","HIGH"],duplicates="drop")
    rows=[]
    for band,g in out.groupby("throughput_band",observed=True):
        rows.append({"hx_id":g.hx_id.iloc[0],"throughput_band":str(band),"record_count":len(g),
                     "relative_ua_empirical_median":g.relative_ua_empirical.median(),
                     "relative_ua_empirical_iqr":g.relative_ua_empirical.quantile(.75)-g.relative_ua_empirical.quantile(.25),
                     "relative_performance_loss_median":g.relative_performance_loss.median()})
    return out,pd.DataFrame(rows)


def period_comparison(frame: pd.DataFrame, spec: dict) -> pd.DataFrame:
    start=pd.Timestamp(spec["start"],tz="Asia/Bangkok");end=pd.Timestamp(spec["end"],tz="Asia/Bangkok")
    periods={"PRE_TAM_30D":(start-pd.Timedelta(days=30),start-pd.Timedelta(days=1)),
             "EMPIRICAL_REFERENCE":(start,end),"LATER_30D":(end+pd.Timedelta(days=1),end+pd.Timedelta(days=30))}
    rows=[]
    for name,(a,b) in periods.items():
        g=frame[(frame.timestamp>=a)&(frame.timestamp<=b)]
        rows.append({"hx_id":spec["hx_id"],"period":name,"start":a,"end":b,"valid_record_count":len(g),
                     "median_ua_kw_k":g.ua_value.median(),"median_u_w_m2_k":g.ua_w_m2_k.median(),
                     "median_relative_ua":g.relative_ua.median(),"median_relative_performance_loss":g.relative_performance_loss.median(),
                     "reference_status":STATUS})
    return pd.DataFrame(rows)


def sensitivity(frame: pd.DataFrame,spec:dict,shifts:list[int])->pd.DataFrame:
    start=pd.Timestamp(spec["start"],tz="Asia/Bangkok");end=pd.Timestamp(spec["end"],tz="Asia/Bangkok");rows=[]
    for ss in shifts:
        for se in shifts:
            a,b=start+pd.Timedelta(days=ss),end-pd.Timedelta(days=se);ref=frame[(frame.timestamp>=a)&(frame.timestamp<=b)]
            if b<a or len(ref)<5:continue
            refua=ref.ua_value.median();relative=frame.ua_value/refua;loss=1-relative
            rows.append({"hx_id":spec["hx_id"],"shift_start_days":ss,"shift_end_days":se,"reference_start":a,"reference_end":b,
                         "reference_valid_record_count":len(ref),"reference_ua_kw_k":refua,"relative_ua_min":relative.min(),"relative_ua_max":relative.max(),
                         "relative_performance_loss_min":loss.min(),"relative_performance_loss_max":loss.max(),"above_reference_pct":(relative>1).mean()*100,
                         "reference_status":STATUS,"clean_condition_confirmed":False})
    return pd.DataFrame(rows)


def _save(fig,path):fig.tight_layout();fig.savefig(path,dpi=140,bbox_inches="tight");plt.close(fig)


def plot_outputs(frame,spec,throughput,periods,sens,out):
    hx=spec["hx_id"];d=out/hx;d.mkdir(parents=True,exist_ok=True);start=pd.Timestamp(spec["start"],tz="Asia/Bangkok");end=pd.Timestamp(spec["end"],tz="Asia/Bangkok")
    fig,axes=plt.subplots(3,1,figsize=(16,10),sharex=True)
    axes[0].plot(frame.timestamp,frame.ua_value,lw=.7);axes[0].axhline(frame.reference_ua.iloc[0],color="green",ls="--",label="Empirical reference UA");axes[0].set_ylabel("UA (kW/K)");axes[0].legend()
    axes[1].plot(frame.timestamp,frame.relative_ua,lw=.7);axes[1].axhline(1,color="green",ls="--");axes[1].set_ylabel("Relative UA (-)")
    axes[2].plot(frame.timestamp,frame.relative_performance_loss,lw=.7);axes[2].axhline(0,color="green",ls="--");axes[2].fill_between(frame.timestamp,frame.relative_performance_loss,0,where=frame.relative_performance_loss<0,color="purple",alpha=.2,label="ABOVE_REFERENCE_PERFORMANCE");axes[2].set_ylabel("Relative performance loss (-)");axes[2].set_xlabel("Time (Asia/Bangkok)");axes[2].legend()
    for ax in axes:ax.axvspan(start,end,color="green",alpha=.12);ax.grid(alpha=.2)
    fig.suptitle(f"{hx} — exploratory empirical-reference performance (NOT CLEAN-STATE FOULING)");_save(fig,d/"01_relative_performance_timelines.png")
    fig,axes=plt.subplots(4,1,figsize=(16,11),sharex=True)
    for ax,col,label in zip(axes,["cold_flow_m3_h","lmtd_value","ua_value","relative_performance_loss"],["Crude flow (m³/h)","LMTD (°C)","UA (kW/K)","Relative performance loss (-)"]):ax.plot(frame.timestamp,frame[col],lw=.7);ax.axvspan(start,end,color="green",alpha=.12);ax.set_ylabel(label);ax.grid(alpha=.2)
    axes[-1].set_xlabel("Time (Asia/Bangkok)");fig.suptitle(f"{hx} — aligned operating conditions and exploratory relative performance");_save(fig,d/"02_aligned_operating_timeline.png")
    fig,axes=plt.subplots(1,3,figsize=(16,5))
    for ax,x,label in zip(axes,["cold_flow_m3_h","lmtd_value","hot_in_c"],["Crude flow (m³/h)","LMTD (°C)","Hot-inlet temperature (°C)"]):ax.scatter(frame[x],frame.relative_performance_loss,s=9,alpha=.4);ax.axhline(0,color="green",ls="--");ax.set_xlabel(label);ax.set_ylabel("Relative performance loss (-)");ax.grid(alpha=.2)
    fig.suptitle(f"{hx} — operating-condition associations (not causal fouling evidence)");_save(fig,d/"03_loss_vs_operating_variables.png")
    fig,ax=plt.subplots(figsize=(8,5));groups=[throughput.loc[throughput.throughput_band==b,"relative_ua"] for b in ["LOW","MEDIUM","HIGH"]];ax.boxplot(groups,tick_labels=["LOW","MEDIUM","HIGH"],showfliers=False);ax.axhline(1,color="green",ls="--");ax.set_ylabel("Relative UA (-)");ax.set_xlabel("Per-HX throughput band");ax.set_title(f"{hx} — relative UA by throughput band");_save(fig,d/"04_relative_ua_by_throughput.png")
    fig,ax=plt.subplots(figsize=(8,5));ax.bar(periods.period,periods.median_relative_ua);ax.axhline(1,color="green",ls="--");ax.set_ylabel("Median relative UA (-)");ax.tick_params(axis='x',rotation=15);ax.set_title(f"{hx} — pre/reference/later comparison");_save(fig,d/"05_period_comparison.png")
    fig,ax=plt.subplots(figsize=(8,5));pivot=sens.pivot(index="shift_start_days",columns="shift_end_days",values="reference_ua_kw_k");im=ax.imshow(pivot,aspect="auto",cmap="viridis");ax.set_xticks(range(len(pivot.columns)),pivot.columns);ax.set_yticks(range(len(pivot.index)),pivot.index);ax.set_xlabel("End shifted inward (days)");ax.set_ylabel("Start shifted inward (days)");ax.set_title(f"{hx} — empirical reference UA sensitivity (kW/K)");fig.colorbar(im,ax=ax);_save(fig,d/"06_reference_sensitivity.png")


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--config",type=Path,default=ROOT/"config/provisional_post_tam_windows.json");ap.add_argument("--physics",type=Path,default=ROOT/"reports/tables/mvp_real_data/hx_physics_validation.csv");args=ap.parse_args();cfg=json.loads(args.config.read_text(encoding="utf-8"));physics=pd.read_csv(args.physics);physics["timestamp"]=pd.to_datetime(physics.timestamp,utc=True).dt.tz_convert("Asia/Bangkok")
    table=ROOT/"reports/tables/mvp_real_data/empirical_relative_performance";fig=ROOT/"reports/figures/mvp_real_data/empirical_relative_performance";table.mkdir(parents=True,exist_ok=True)
    frames=[];summaries=[];rels=[];bands=[];periods=[];sensitivities=[]
    for spec in cfg["windows"]:
        frame,summary=calculate_relative_performance(physics,spec);throughput,band=throughput_distribution(frame);period=period_comparison(frame,spec);sens=sensitivity(frame,spec,cfg["sensitivity_inward_shift_days"]);plot_outputs(frame,spec,throughput,period,sens,fig)
        frames.append(frame);summaries.append(summary);rels.append(relationship_summary(frame));bands.append(band);periods.append(period);sensitivities.append(sens)
    pd.concat(frames,ignore_index=True).to_csv(table/"relative_performance_timeseries.csv",index=False);pd.DataFrame(summaries).to_csv(table/"exploratory_summary.csv",index=False);pd.concat(rels).to_csv(table/"operating_relationships.csv",index=False);pd.concat(bands).to_csv(table/"throughput_band_distribution.csv",index=False);pd.concat(periods).to_csv(table/"period_comparison.csv",index=False);pd.concat(sensitivities).to_csv(table/"reference_sensitivity.csv",index=False)
    print(pd.DataFrame(summaries)[["hx_id","reference_ua","valid_record_count","records_above_reference_pct","impact_status"]].to_string(index=False))


if __name__=="__main__":main()
