"""Transparent F101 duty estimate and exploratory fuel-gas calibration."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.validation.real_data import load_dcs_matrix,load_pilot_config,resolve_tag

def furnace_duty_kw(mass_flow_kg_s,cp_kj_kg_k,cit_c,cot_c):
    values=np.asarray([mass_flow_kg_s,cp_kj_kg_k,cit_c,cot_c],dtype=float)
    if not np.isfinite(values).all() or mass_flow_kg_s<=0 or cp_kj_kg_k<=0 or cot_c<=cit_c:return np.nan
    return float(mass_flow_kg_s*cp_kj_kg_k*(cot_c-cit_c))

def build_furnace_timeseries(physics,raw,cfg):
    aliases=cfg.get("aliases",{});tags={name:resolve_tag(raw.columns,tag,aliases) for name,tag in {"measured_cit_c":"1TI116.pv","measured_cot_c":"1TI150.pv","fuel_gas_knm3_h":"1FI028.pv","flue_o2_pct":"1AI001.pv","stack_temp_c":"1TI153.pv","draft":"1PC034.pv"}.items()}
    base=physics[(physics.hx_id=="E113A") & physics.operating_valid].copy()
    measurements=pd.DataFrame({"timestamp":raw.timestamp})
    for name,tag in tags.items():measurements[name]=pd.to_numeric(raw[tag],errors="coerce") if tag else np.nan
    out=base.merge(measurements,on="timestamp",how="left")
    out["f101_duty_physics_kw"]=[furnace_duty_kw(r.mass_flow_value,r.cp_kj_kg_k,r.measured_cit_c,r.measured_cot_c) for r in out.itertuples()]
    out["f101_duty_status"]=np.where(out.f101_duty_physics_kw.notna(),"PROVISIONAL","UNAVAILABLE")
    out["f101_duty_basis"]="mass_flow_kg_s * Cp_kJ_kg_K * (COT - CIT)"
    out["fuel_penalty_status"]="BLOCKED";out["fuel_penalty_blocker"]="NO_APPROVED_FUEL_LHV_AND_FURNACE_EFFICIENCY"
    return out,tags

def calibration_summary(frame):
    data=frame[["f101_duty_physics_kw","fuel_gas_knm3_h"]].dropna()
    if len(data)<60:return {"status":"PARTIAL","valid_records":len(data),"reason":"INSUFFICIENT_PAIRED_DUTY_FG_DATA"}
    split=int(len(data)*.8);train,test=data.iloc[:split],data.iloc[split:];x=np.c_[np.ones(len(train)),train.f101_duty_physics_kw];beta=np.linalg.lstsq(x,train.fuel_gas_knm3_h,rcond=None)[0];pred=np.c_[np.ones(len(test)),test.f101_duty_physics_kw]@beta;actual=test.fuel_gas_knm3_h.to_numpy();persist=np.repeat(train.fuel_gas_knm3_h.iloc[-1],len(test))
    return {"status":"EXPLORATORY","valid_records":len(data),"model":"LINEAR_FG_VS_PHYSICS_DUTY","intercept_knm3_h":beta[0],"slope_knm3_h_per_kw":beta[1],"holdout_rmse_knm3_h":float(np.sqrt(np.mean((actual-pred)**2))),"persistence_rmse_knm3_h":float(np.sqrt(np.mean((actual-persist)**2))),"causal_efficiency_interpretation_allowed":False}

def main():
    cfg=load_pilot_config(ROOT/"config/mvp_real_data_pilot.json");raw,_=load_dcs_matrix(cfg);p=pd.read_csv(ROOT/"reports/tables/mvp_real_data/hx_physics_validation.csv");p["timestamp"]=pd.to_datetime(p.timestamp,utc=True).dt.tz_convert(cfg["dataset"]["timezone"]);frame,tags=build_furnace_timeseries(p,raw,cfg);summary=calibration_summary(frame);tables=ROOT/"reports/tables/mvp_real_data/f101_consequence";figures=ROOT/"reports/figures/mvp_real_data/f101_consequence";tables.mkdir(parents=True,exist_ok=True);figures.mkdir(parents=True,exist_ok=True);frame.to_csv(tables/"f101_physics_timeseries.csv",index=False);pd.DataFrame([{**summary,"physics_estimate_status":"PROVISIONAL","fuel_penalty_status":"BLOCKED","throughput_headroom_status":"BLOCKED","network_predicted_cit_used":False,"measured_cit_used":True,"blocker":"NETWORK_NOT_VALIDATED; NO_APPROVED_LHV_OR_EFFICIENCY"}]).to_csv(tables/"f101_consequence_summary.csv",index=False);pd.DataFrame([{"variable":k,"source_tag":v or "","status":"VALIDATED" if v else "UNAVAILABLE"} for k,v in tags.items()]).to_csv(tables/"f101_input_register.csv",index=False)
    v=frame.dropna(subset=["f101_duty_physics_kw"]);fig,axes=plt.subplots(2,1,figsize=(15,8),sharex=True);axes[0].plot(v.timestamp,v.f101_duty_physics_kw,lw=.7,label="Physics estimate");axes[0].set_ylabel("F101 duty (kW)");axes[0].legend();axes[1].plot(v.timestamp,v.fuel_gas_knm3_h,lw=.7,label="Measured fuel gas");axes[1].set_ylabel("Fuel gas (kNm3/h)");axes[1].set_xlabel("Time (Asia/Bangkok)");axes[1].legend();fig.suptitle("F101 consequence screening - measured inputs and provisional physics estimate");fig.tight_layout();fig.savefig(figures/"f101_duty_and_fuel_timeline.png",dpi=140);plt.close(fig)
    paired=v.dropna(subset=["fuel_gas_knm3_h","measured_cit_c"]);fig,axes=plt.subplots(1,2,figsize=(12,5));axes[0].scatter(paired.measured_cit_c,paired.f101_duty_physics_kw,s=8,alpha=.35);axes[0].set(xlabel="Measured CIT (degC)",ylabel="F101 physics duty (kW)");axes[1].scatter(paired.measured_cit_c,paired.fuel_gas_knm3_h,s=8,alpha=.35);axes[1].set(xlabel="Measured CIT (degC)",ylabel="Measured fuel gas (kNm3/h)");fig.suptitle("F101 exploratory CIT relationships (not causal efficiency)");fig.tight_layout();fig.savefig(figures/"f101_cit_relationships.png",dpi=140);plt.close(fig)
    if len(paired)>=60:
        split=int(len(paired)*.8);train,test=paired.iloc[:split],paired.iloc[split:];x=np.c_[np.ones(len(train)),train.f101_duty_physics_kw];beta=np.linalg.lstsq(x,train.fuel_gas_knm3_h,rcond=None)[0];pred=np.c_[np.ones(len(test)),test.f101_duty_physics_kw]@beta;fig,ax=plt.subplots(figsize=(6,6));ax.scatter(test.fuel_gas_knm3_h,pred,s=10,alpha=.5);lo=min(test.fuel_gas_knm3_h.min(),pred.min());hi=max(test.fuel_gas_knm3_h.max(),pred.max());ax.plot([lo,hi],[lo,hi],"k--");ax.set(xlabel="Measured fuel gas (kNm3/h)",ylabel="Predicted fuel gas (kNm3/h)",title="F101 chronological holdout diagnostics");ax.grid(alpha=.2);fig.tight_layout();fig.savefig(figures/"f101_fuel_model_diagnostics.png",dpi=140);plt.close(fig)
    limits={row["id"]:row["value"] for row in json.loads((ROOT/"config/plant_limits.json").read_text(encoding="utf-8"))["records"]};m=v.dropna(subset=["measured_cit_c","measured_cot_c"]);fig,ax=plt.subplots(figsize=(14,5));ax.plot(m.timestamp,m.measured_cit_c-limits["CIT_FLOOR"],label="CIT margin above floor");ax.plot(m.timestamp,limits["COT_LIMIT"]-m.measured_cot_c,label="COT headroom below limit");ax.axhline(0,color="red",ls="--");ax.set(xlabel="Time (Asia/Bangkok)",ylabel="Temperature margin (degC)",title="Measured F101 CIT/COT operating margins");ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(figures/"f101_cit_cot_margin.png",dpi=140);plt.close(fig);print(summary)
if __name__=="__main__":main()
