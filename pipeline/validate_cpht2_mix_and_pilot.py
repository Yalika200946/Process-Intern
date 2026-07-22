"""CPHT-2 split/mix closure, continuity, residue response, and pilot gates."""
from __future__ import annotations
import json, sys
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from pipeline.run_critical_correction_batch import validate_branch_15
from src.network.validation import (classify_configuration_response, continuity_assessment,
    closure_case_kind, enthalpy_weighted_mix_temperature, evaluate_network_gates, flow_tolerance_sensitivity,
    segment_event_window)
from src.validation.real_data import load_dcs_matrix,load_pilot_config,resolve_tag

BASE=ROOT/"reports/tables/mvp_real_data"; OUT=BASE/"cpht2_mix_validation"; FIG=ROOT/"reports/figures/mvp_real_data/cpht2_mix_validation"
BRANCHES={"BRANCH_1FI016":["E106AB","E107AB","E108AB","E109AB"],
          "BRANCH_1FI017":["E110ABC","E111","E112AB"],
          "BRANCH_1FI015":["E103AB","E104","E105AB"]}

def node_registry(cfg,top):
    rows=[]
    for branch,seq in BRANCHES.items():
        for order,hx in enumerate(seq):
            spec=cfg["heat_exchangers"][hx]
            rows.append({"node_id":f"{branch}_{order}_{hx}","upstream_equipment":seq[order-1] if order else "CPHT2_SPLIT",
                "downstream_equipment":seq[order+1] if order+1<len(seq) else "CPHT2_MIX",
                "stream_side":"CRUDE","measured_temperature_tag":spec["cold_out"],"inferred_temperature":False,
                "flow_tag":spec["cold_flow"],"flow_basis":spec.get("flow_kind","MEASURED"),"branch_id":branch,
                "split_or_mix":"BRANCH_INTERNAL","configuration_dependency":"NONE" if hx not in {"E108AB","E112AB"} else "RESIDUE_LINEUP",
                "data_kind":"MEASURED","confidence":"HIGH","blocker":""})
    residue=top["hot_stream_side"]["residue_sequence"]
    for i,hx in enumerate(residue):
        rows.append({"node_id":f"RESIDUE_{i}_{hx}","upstream_equipment":residue[i-1] if i else "P110_RESIDUE",
            "downstream_equipment":residue[i+1] if i+1<len(residue) else "RESIDUE_DOWNSTREAM",
            "stream_side":"RESIDUE_HOT","measured_temperature_tag":"SEE_HX_MAPPING","inferred_temperature":hx=="E112AB",
            "flow_tag":"UNCONFIRMED_RESIDUE_FLOW_BASIS","flow_basis":"UNAVAILABLE","branch_id":"RESIDUE_PATH",
            "split_or_mix":"CONFIGURATION_DEPENDENT","configuration_dependency":"CLEANING_SUBSTITUTION_RULES",
            "data_kind":"INFERRED" if hx=="E112AB" else "MEASURED","confidence":"MEDIUM","blocker":"NO_VALVE_HISTORY"})
    rows += [{"node_id":"CPHT2_SPLIT","upstream_equipment":"D103","downstream_equipment":"THREE_CRUDE_BRANCHES","stream_side":"CRUDE","measured_temperature_tag":"1TI225.pv","inferred_temperature":False,"flow_tag":"1fi005.pv","flow_basis":"TOTAL_MEASURED","branch_id":"COMMON","split_or_mix":"SPLIT","configuration_dependency":"NONE","data_kind":"MEASURED","confidence":"HIGH","blocker":""},
             {"node_id":"CPHT2_MIX","upstream_equipment":"THREE_BRANCH_OUTLETS","downstream_equipment":"E113A_OR_E112C","stream_side":"CRUDE","measured_temperature_tag":"1TI115.pv","inferred_temperature":False,"flow_tag":"1fi005.pv","flow_basis":"TOTAL_MEASURED","branch_id":"COMMON","split_or_mix":"MIX","configuration_dependency":"RESIDUE_LINEUP","data_kind":"MEASURED","confidence":"MEDIUM","blocker":"ENGINEERING_ERROR_THRESHOLD_REQUIRED"}]
    return pd.DataFrame(rows)

def enriched_flow(raw,cfg):
    aliases=cfg.get("aliases",{}); tag=lambda x:resolve_tag(raw.columns,x,aliases)
    def num(x):
        t=tag(x);return pd.to_numeric(raw[t],errors="coerce") if t else pd.Series(np.nan,index=raw.index)
    out=pd.DataFrame({"timestamp":raw.timestamp,"total_flow":num("1fi005.pv"),"branch_flow_1":num("1FI016.pv"),"branch_flow_2":num("1FI017.pv"),"branch_flow_3":num("1FI015.pv")})
    out["flow_sum"]=out[["branch_flow_1","branch_flow_2","branch_flow_3"]].sum(axis=1,min_count=3)
    out["residual"]=out.total_flow-out.flow_sum;out["absolute_residual"]=out.residual.abs();out["relative_residual"]=out.residual/out.total_flow
    out["operating_state"]=np.where(out.total_flow<50,"SHUTDOWN",np.where(out[["branch_flow_1","branch_flow_2","branch_flow_3"]].min(axis=1)<=15,"TRANSITION","NORMAL"))
    out["configuration_state"]="BASE_LINEUP_NO_VALVE_CONFIRMATION"
    out["within_tolerance"]=out.relative_residual.abs().le(.15);out["tolerance_status"]="ANALYTICAL_SCREENING_TOLERANCE"
    out["valid_for_mix_validation"]=out.operating_state.eq("NORMAL")&out.within_tolerance&np.isfinite(out[["total_flow","flow_sum"]]).all(axis=1)
    out["throughput_band"]=pd.qcut(out.total_flow.rank(method="first"),3,labels=["LOW","MEDIUM","HIGH"])
    out["time_period"]=pd.to_datetime(out.timestamp).dt.year
    return out

def mix_closure(physics,flow):
    fields=["cold_out_c","mass_flow_value","cp_kj_kg_k","operating_valid","data_kind","sg_15_6c"]
    frames=[]
    for hx,label in [("E109AB","b1"),("E112AB","b2"),("E105AB","b3")]:
        g=physics[physics.hx_id.eq(hx)].set_index("timestamp")[fields].add_suffix("_"+label);frames.append(g)
    measured=physics[physics.hx_id.eq("E113A")].set_index("timestamp")[["cold_in_c","data_available"]].rename(columns={"cold_in_c":"mix_measured_c","data_available":"mix_sensor_available"})
    j=frames[0].join(frames[1:]+[measured],how="inner").reset_index(); f=flow.copy();f["timestamp"]=pd.to_datetime(f.timestamp)
    j["timestamp"]=pd.to_datetime(j.timestamp);j=j.merge(f[["timestamp","total_flow","relative_residual","within_tolerance","valid_for_mix_validation","throughput_band","operating_state","configuration_state"]],on="timestamp",how="left")
    predicted=[];valid=[];warning=[];lo=[];hi=[]
    for r in j.itertuples():
        result=enthalpy_weighted_mix_temperature([r.mass_flow_value_b1,r.mass_flow_value_b2,r.mass_flow_value_b3],[r.cp_kj_kg_k_b1,r.cp_kj_kg_k_b2,r.cp_kj_kg_k_b3],[r.cold_out_c_b1,r.cold_out_c_b2,r.cold_out_c_b3])
        predicted.append(result.get("value"));valid.append(result["is_valid"]);warning.append(result["warning_code"]);lo.append(result.get("inlet_min_c"));hi.append(result.get("inlet_max_c"))
    j["mix_predicted_c"]=predicted;j["mix_physical_valid"]=valid;j["warning_code"]=warning;j["inlet_min_c"]=lo;j["inlet_max_c"]=hi
    j["closure_case_kind"]=j[["data_kind_b1","data_kind_b2","data_kind_b3"]].apply(lambda row:closure_case_kind(row),axis=1)
    j["fully_measured_case"]=j.closure_case_kind.eq("FULLY_MEASURED")
    j["measured_mix_within_inlet_bounds"] = j.mix_measured_c.between(j.inlet_min_c-3.0, j.inlet_max_c+3.0)
    j.loc[~j.measured_mix_within_inlet_bounds.fillna(False),"warning_code"] = "MEASURED_MIX_NODE_INCONSISTENT_WITH_BRANCH_OUTLETS"
    j["closure_valid"]=j.valid_for_mix_validation.fillna(False)&j.mix_physical_valid&j.measured_mix_within_inlet_bounds.fillna(False)&j.mix_sensor_available.astype(bool)&j[["operating_valid_b1","operating_valid_b2","operating_valid_b3"]].all(axis=1)
    j["residual_C"]=j.mix_predicted_c-j.mix_measured_c;j["absolute_error_C"]=j.residual_C.abs()
    return j

def metric_table(mix):
    rows=[]
    for scope,g in [("ALL_VALID",mix[mix.closure_valid])]+[(f"THROUGHPUT_{k}",v[v.closure_valid]) for k,v in mix.groupby("throughput_band",observed=True)]:
        err=g.residual_C.dropna();rows.append({"scope":scope,"valid_record_count":len(err),"validation_coverage_pct":100*len(err)/len(mix),"MAE_C":err.abs().mean(),"RMSE_C":np.sqrt((err**2).mean()),"bias_C":err.mean(),"median_absolute_error_C":err.abs().median(),"P90_absolute_error_C":err.abs().quantile(.9),"engineering_status":"ENGINEERING_THRESHOLD_REQUIRED"})
    return pd.DataFrame(rows)

def continuity(cfg):
    rows=[]
    for branch,seq in BRANCHES.items():
        for a,b in zip(seq,seq[1:]):
            at=cfg["heat_exchangers"][a]["cold_out"];bt=cfg["heat_exchangers"][b]["cold_in"]
            rows.append({"branch_id":branch,"upstream_hx":a,"downstream_hx":b,"upstream_out_tag":at,"downstream_in_tag":bt,**continuity_assessment(str(at),str(bt))})
    return pd.DataFrame(rows)

def residue_responses(physics,events):
    rows=[]
    for e in events[events.hx_id.isin(["E113A","E112C","E112AB","E108AB"])].itertuples():
        g=physics[physics.hx_id.eq(e.hx_id)].copy();g["timestamp"]=pd.to_datetime(g.timestamp)
        if g.empty:
            rows.append({"event_id":e.event_id,"hx_id":e.hx_id,"event_timestamp":e.event_timestamp,"classification":"INSUFFICIENT_EVIDENCE","pre_valid_records":0,"post_valid_records":0,"confirmed_cleaning_events":0});continue
        seg=segment_event_window(g.timestamp,e.event_timestamp);valid=g.operating_valid.astype(bool)&g.ua_valid.astype(bool);pre=g[valid&seg.eq("PRE")];post=g[valid&seg.eq("POST")]
        med=lambda frame,col:frame[col].median() if len(frame) else np.nan
        change=lambda col:(med(post,col)/med(pre,col)-1) if len(pre) and med(pre,col) not in (0,np.nan) else np.nan
        uc,fc,lc=change("ua_value"),change("cold_flow_m3_h"),change("lmtd_value")
        cls=classify_configuration_response(pre_count=len(pre),post_count=len(post),ua_change_fraction=uc if np.isfinite(uc) else 0,flow_change_fraction=fc if np.isfinite(fc) else 9,lmtd_change_fraction=lc if np.isfinite(lc) else 9,sensor_valid=bool(len(pre) and len(post)),original_rejected=e.event_status=="REJECTED_SIGNAL_EVENT")
        rows.append({"event_id":e.event_id,"hx_id":e.hx_id,"event_timestamp":e.event_timestamp,"original_status":e.event_status,"pre_valid_records":len(pre),"post_valid_records":len(post),"pre_median_ua":med(pre,"ua_value"),"post_median_ua":med(post,"ua_value"),"ua_relative_change":uc,"flow_relative_change":fc,"lmtd_relative_change":lc,"pre_ua_iqr":pre.ua_value.quantile(.75)-pre.ua_value.quantile(.25) if len(pre) else np.nan,"post_ua_iqr":post.ua_value.quantile(.75)-post.ua_value.quantile(.25) if len(post) else np.nan,"operating_condition_comparable":bool(np.isfinite(fc) and np.isfinite(lc) and abs(fc)<=.1 and abs(lc)<=.1),"temperature_response_consistency":"SCREENED","performance_response_consistency":cls,"classification":cls,"confirmed_cleaning_events":0})
    return pd.DataFrame(rows)

def branch_ranking(physics,flow,cont):
    rows=[];total=physics.timestamp.nunique();flow_score=20*flow.within_tolerance.mean()
    refs={"BRANCH_1FI015":5,"BRANCH_1FI016":0,"BRANCH_1FI017":0};config={"BRANCH_1FI015":10,"BRANCH_1FI016":5,"BRANCH_1FI017":5}
    for branch,seq in BRANCHES.items():
        coverage=min((physics[physics.hx_id.eq(h)].operating_valid.astype(bool).sum()/total for h in seq))*10
        continuity_score=15 if (cont[cont.branch_id.eq(branch)].continuity_status=="SHARED_TAG_NOT_INDEPENDENT").all() else 5
        score=20+flow_score+continuity_score+15+config[branch]+coverage+refs[branch]
        rows.append({"branch_id":branch,"sequence":" -> ".join(seq),"branch_readiness_score":score,"readiness_status":"PROVISIONAL" if score>=70 else "PARTIAL","critical_blockers":"ENGINEERING_ERROR_THRESHOLD;SHARED_TAGS_NOT_INDEPENDENT","available_measured_nodes":len(seq)+1,"usable_time_periods":"OPERATING_VALID_AND_FLOW_BALANCED","validation_scope":"TEMPERATURE_PROPAGATION_ONLY"})
    return pd.DataFrame(rows).sort_values("branch_readiness_score",ascending=False)

def plots(mix):
    valid=mix[mix.closure_valid].copy()
    specs=[("measured_vs_predicted",valid.mix_measured_c,valid.mix_predicted_c,"Measured mix (degC)","Predicted mix (degC)"),("residual_vs_flow",valid.total_flow,valid.residual_C,"Total flow (m3/h)","Residual (degC)"),("residual_vs_flow_error",valid.relative_residual,valid.residual_C,"Flow relative residual (-)","Temperature residual (degC)")]
    for name,x,y,xlabel,ylabel in specs:
        fig,ax=plt.subplots(figsize=(7,5));ax.scatter(x,y,s=10,alpha=.5);ax.set(xlabel=xlabel,ylabel=ylabel,title=name.replace('_',' ').title());ax.grid(alpha=.2);fig.tight_layout();fig.savefig(FIG/f"{name}.png",dpi=140);plt.close(fig)
    fig,ax=plt.subplots(figsize=(14,4));ax.plot(valid.timestamp,valid.residual_C,lw=.7);ax.axhline(0,color="black",lw=.7);ax.set(xlabel="Time",ylabel="Residual (degC)",title="Mix-temperature residual over time");ax.grid(alpha=.2);fig.tight_layout();fig.savefig(FIG/"residual_over_time.png",dpi=140);plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,5));ax.hist(valid.residual_C,bins=35);ax.set(xlabel="Residual (degC)",ylabel="Count",title="Mix residual distribution");fig.tight_layout();fig.savefig(FIG/"residual_distribution.png",dpi=140);plt.close(fig)
    fig,ax=plt.subplots(figsize=(14,5));ax.plot(valid.timestamp,valid.cold_out_c_b1,label="Branch 016 out",alpha=.6);ax.plot(valid.timestamp,valid.cold_out_c_b2,label="Branch 017 out",alpha=.6);ax.plot(valid.timestamp,valid.cold_out_c_b3,label="Branch 015 out",alpha=.6);ax.plot(valid.timestamp,valid.mix_measured_c,label="Measured mix",lw=1);ax.plot(valid.timestamp,valid.mix_predicted_c,label="Predicted mix",lw=1);ax.set(ylabel="Temperature (degC)",xlabel="Time");ax.legend(ncol=5);ax.grid(alpha=.2);fig.tight_layout();fig.savefig(FIG/"inlets_and_mix_temperature.png",dpi=140);plt.close(fig)

def main():
    OUT.mkdir(parents=True,exist_ok=True);FIG.mkdir(parents=True,exist_ok=True)
    cfg=load_pilot_config(ROOT/"config/mvp_real_data_pilot.json");top=json.loads((ROOT/"config/configuration_topology.json").read_text(encoding="utf-8"));raw,_=load_dcs_matrix(cfg);physics=pd.read_csv(BASE/"hx_physics_validation.csv",parse_dates=["timestamp"]);events=pd.read_csv(BASE/"signal_inferred_cleaning/signal_recovery_candidates.csv")
    nodes=node_registry(cfg,top);flow=enriched_flow(raw,cfg);mix=mix_closure(physics,flow);metrics=metric_table(mix);cont=continuity(cfg);responses=residue_responses(physics,events);ranking=branch_ranking(physics,flow,cont);pilot_ts,pilot_metrics=validate_branch_15(physics)
    sensitivity=flow_tolerance_sensitivity(flow.loc[flow.operating_state.eq("NORMAL"),"relative_residual"])
    flow_summary=flow.groupby(["operating_state","throughput_band","time_period"],observed=True).agg(records=("timestamp","size"),median_residual=("residual","median"),median_relative_residual=("relative_residual","median"),within_15pct=("within_tolerance","mean")).reset_index()
    gates={"Gate A - Flow split":"PASS_PROVISIONAL" if flow.loc[flow.operating_state.eq("NORMAL"),"within_tolerance"].mean()>=.90 else "FAIL","Gate B - Mix-temperature closure":"ENGINEERING_THRESHOLD_REQUIRED","Gate C - Temperature continuity":"PASS_PROVISIONAL" if cont.usable_for_network.all() else "FAIL","Gate D - Configuration response":"PASS_PROVISIONAL" if len(responses) else "BLOCKED","Gate E - Pilot propagation":"ENGINEERING_THRESHOLD_REQUIRED"}
    decision=evaluate_network_gates(gates);gate=pd.DataFrame([{"gate":k,"status":v,"basis":"Analytical result; plant acceptance threshold not supplied."} for k,v in gates.items()]);gate["network_status"]=decision["network_status"]
    for name,frame in [("cpht2_node_registry",nodes),("cpht2_flow_validation",flow),("flow_tolerance_sensitivity",sensitivity),("flow_residual_stratification",flow_summary),("mix_temperature_closure",mix),("mix_temperature_metrics",metrics),("temperature_continuity",cont),("residue_event_response",responses),("pilot_branch_ranking",ranking),("pilot_network_validation_timeseries",pilot_ts),("pilot_network_validation_metrics",pilot_metrics),("network_gates",gate)]:frame.to_csv(OUT/f"{name}.csv",index=False)
    (OUT/"network_status.json").write_text(json.dumps({**decision,"primary_pilot_branch":ranking.iloc[0].branch_id,"backup_pilot_branch":ranking.iloc[1].branch_id,"full_network_validated":False},indent=2),encoding="utf-8")
    plots(mix);print(metrics.to_string(index=False));print(ranking.to_string(index=False));print(gate.to_string(index=False))
if __name__=="__main__":main()
