"""Exploratory HX-to-measured-CIT screening; association is not cleaning benefit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.validation.real_data import load_dcs_matrix,load_pilot_config,resolve_tag

CIT_TAG="1TI116.pv"
MINIMUM=60


def partial_correlation(frame:pd.DataFrame,x:str,y:str,controls:list[str])->float:
    data=frame[[x,y,*controls]].dropna()
    if len(data)<5:return np.nan
    c=np.c_[np.ones(len(data)),data[controls].to_numpy(float)]
    rx=data[x].to_numpy(float)-c@np.linalg.lstsq(c,data[x].to_numpy(float),rcond=None)[0]
    ry=data[y].to_numpy(float)-c@np.linalg.lstsq(c,data[y].to_numpy(float),rcond=None)[0]
    return float(np.corrcoef(rx,ry)[0,1]) if np.std(rx)>0 and np.std(ry)>0 else np.nan


def screen_relationships(physics:pd.DataFrame,cit:pd.DataFrame,minimum:int=MINIMUM)->tuple[pd.DataFrame,pd.DataFrame]:
    merged=physics.merge(cit,on="timestamp",how="left")
    rows=[];models=[]
    variables=["ua_w_m2_k","q_cold_value","cold_out_c","lmtd_value","cold_flow_m3_h","hot_in_c"]
    controls=["cold_flow_m3_h","sg_15_6c","cold_in_c","hot_in_c"]
    for hx_id,g in merged.groupby("hx_id"):
        valid=g[g.operating_valid & g.ua_valid].sort_values("timestamp").copy()
        target_leak=hx_id=="E113A"
        for x in variables:
            selected=list(dict.fromkeys(["timestamp",x,"measured_cit_c",*controls]))
            pair=valid[selected].dropna().drop_duplicates()
            best_lag=np.nan;best_corr=np.nan
            if len(pair)>=minimum:
                lag_values=[]
                indexed=valid.set_index("timestamp")[[x,"measured_cit_c"]].dropna()
                for lag in range(-7,8):
                    value=indexed[x].corr(indexed.measured_cit_c.shift(-lag),method="spearman")
                    lag_values.append((lag,value))
                finite=[item for item in lag_values if np.isfinite(item[1])]
                if finite:best_lag,best_corr=max(finite,key=lambda item:abs(item[1]))
            direct_leak=target_leak and x=="cold_out_c"
            rows.append({"hx_id":hx_id,"x_variable":x,"target":"measured_cit_c",
                "valid_sample_count":len(pair),"pearson":pair[x].corr(pair.measured_cit_c,method="pearson") if len(pair)>=minimum else np.nan,
                "spearman":pair[x].corr(pair.measured_cit_c,method="spearman") if len(pair)>=minimum else np.nan,
                "partial_correlation":partial_correlation(pair,x,"measured_cit_c",[c for c in controls if c!=x]) if len(pair)>=minimum else np.nan,
                "best_lag_days":best_lag,"best_lag_spearman":best_corr,"coefficient_sign":None,
                "status":"EXPLORATORY" if len(pair)>=minimum else "PARTIAL",
                "target_leakage_warning":"DIRECT_CIT_IDENTITY" if direct_leak else ("CIT_DERIVED_FEATURE_DEPENDENCE" if target_leak else ""),
                "causal_or_cleaning_benefit_interpretation_allowed":False})
        feature_cols=["ua_w_m2_k","q_cold_value","lmtd_value","cold_flow_m3_h","hot_in_c","cold_in_c","sg_15_6c"]
        model=valid[feature_cols+["measured_cit_c"]].dropna()
        if len(model)<minimum:
            models.append({"hx_id":hx_id,"status":"PARTIAL","valid_sample_count":len(model),"reason":"INSUFFICIENT_COMPLETE_CASES"});continue
        split=int(len(model)*.8);train,test=model.iloc[:split],model.iloc[split:];mean=train[feature_cols].mean();std=train[feature_cols].std().replace(0,1)
        x=np.c_[np.ones(len(train)),((train[feature_cols]-mean)/std).to_numpy()];pen=np.eye(x.shape[1]);pen[0,0]=0
        beta=np.linalg.solve(x.T@x+pen,x.T@train.measured_cit_c.to_numpy());xt=np.c_[np.ones(len(test)),((test[feature_cols]-mean)/std).to_numpy()];pred=xt@beta
        persistence=np.repeat(train.measured_cit_c.iloc[-1],len(test));actual=test.measured_cit_c.to_numpy()
        models.append({"hx_id":hx_id,"status":"EXPLORATORY","valid_sample_count":len(model),"train_count":len(train),"test_count":len(test),
            "model":"RIDGE_INTERPRETABLE_SCREENING","holdout_rmse_c":float(np.sqrt(np.mean((actual-pred)**2))),
            "persistence_rmse_c":float(np.sqrt(np.mean((actual-persistence)**2))),"target_leakage_warning":"CIT_DERIVED_FEATURE_DEPENDENCE" if target_leak else "",
            "network_cleaning_benefit_claim_allowed":False})
    return pd.DataFrame(rows),pd.DataFrame(models)


def plot_screening(physics,cit,out):
    merged=physics.merge(cit,on="timestamp",how="left");out.mkdir(parents=True,exist_ok=True)
    for hx_id,g in merged.groupby("hx_id"):
        v=g[g.operating_valid & g.ua_valid].dropna(subset=["ua_w_m2_k","measured_cit_c"])
        if len(v)<MINIMUM:continue
        fig,axes=plt.subplots(1,2,figsize=(13,5));axes[0].scatter(v.ua_w_m2_k,v.measured_cit_c,s=8,alpha=.35);axes[0].set(xlabel="U (W/m2-K)",ylabel="Measured CIT (degC)")
        axes[1].plot(v.timestamp,v.measured_cit_c,label="Measured CIT",lw=.7);ax=axes[1].twinx();ax.plot(v.timestamp,v.ua_w_m2_k,color="tab:orange",label="Calculated U",lw=.6,alpha=.7);axes[1].set_ylabel("Measured CIT (degC)");ax.set_ylabel("U (W/m2-K)");axes[1].set_xlabel("Time (Asia/Bangkok)")
        fig.suptitle(f"{hx_id} - exploratory HX-CIT association (not cleaning benefit)");fig.tight_layout();fig.savefig(out/f"{hx_id}_cit_screening.png",dpi=140,bbox_inches="tight");plt.close(fig)


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--config",type=Path,default=ROOT/"config/mvp_real_data_pilot.json");ap.add_argument("--physics",type=Path,default=ROOT/"reports/tables/mvp_real_data/hx_physics_validation.csv");args=ap.parse_args()
    cfg=load_pilot_config(args.config);raw,_=load_dcs_matrix(cfg);tag=resolve_tag(raw.columns,CIT_TAG,cfg.get("aliases",{}));
    if tag is None:raise ValueError(f"Measured CIT tag unavailable: {CIT_TAG}")
    cit=pd.DataFrame({"timestamp":raw.timestamp,"measured_cit_c":pd.to_numeric(raw[tag],errors="coerce")});physics=pd.read_csv(args.physics);physics["timestamp"]=pd.to_datetime(physics.timestamp,utc=True).dt.tz_convert(cfg["dataset"]["timezone"])
    relationships,models=screen_relationships(physics,cit);tables=ROOT/"reports/tables/mvp_real_data/hx_cit_screening";figures=ROOT/"reports/figures/mvp_real_data/hx_cit_screening";tables.mkdir(parents=True,exist_ok=True)
    relationships.to_csv(tables/"hx_cit_relationships.csv",index=False);models.to_csv(tables/"hx_cit_model_validation.csv",index=False);pd.DataFrame([{"target_tag":tag,"target_unit":"degC","status":"EXPLORATORY","interpretation":"Association only; not cleaning benefit or network recovery."}]).to_csv(tables/"cit_target_register.csv",index=False);plot_screening(physics,cit,figures)
    print(relationships.status.value_counts().to_string())
if __name__=="__main__":main()
