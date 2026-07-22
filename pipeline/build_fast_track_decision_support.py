"""Interim evidence monitoring and cleaning-action review; no final recommendations."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import matplotlib.pyplot as plt
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.domain.bypass import feasibility_label

def build_priorities(config,coverage,events,relative,forecast):
    event_count=events[events.evidence_level.isin(["CLEANING_CANDIDATE","SHELL_SWITCH_OR_BYPASS_CANDIDATE"])].groupby("hx_id").size()
    latest=relative.sort_values("timestamp").groupby("hx_id").tail(1).set_index("hx_id") if len(relative) else pd.DataFrame()
    slopes=forecast.set_index("hx_id") if len(forecast) else pd.DataFrame()
    rows=[]
    for hx_id,hx in config["heat_exchangers"].items():
        cov=float(coverage.loc[hx_id,"ua_valid"] if hx_id in coverage.index else 0);candidates=int(event_count.get(hx_id,0));loss=float(latest.loc[hx_id,"relative_performance_loss"]) if hx_id in latest.index else None;slope=float(slopes.loc[hx_id,"slope_relative_ua_per_day"]) if hx_id in slopes.index else None
        data_ok=cov>=50 and hx.get("status") not in {"BLOCKED","UNAVAILABLE"};score=(2 if data_ok else 0)+(3 if candidates else 0)+(min(max(loss or 0,0),1)*2 if loss is not None else 0)+(1 if slope is not None and slope<0 else 0)
        if not data_ok:status="INSUFFICIENT_EVIDENCE"
        elif candidates:status="NEEDS_ENGINEERING_REVIEW"
        else:status="MONITOR"
        rows.append({"hx_id":hx_id,"monitoring_priority_score":score,"condition_status":"PROVISIONAL" if loss is not None else "PARTIAL","latest_relative_performance_loss":loss,"forecast_slope_per_day":slope,"candidate_signal_count":candidates,"ua_valid_coverage_pct":cov,"feasibility":feasibility_label(hx_id),"network_consequence_status":"BLOCKED","furnace_consequence_status":"BLOCKED","economics_status":"BLOCKED","recommendation_status":status,"final_cleaning_recommendation":False,"reason":"Network consequence, economics, and confirmed maintenance evidence are incomplete."})
    out=pd.DataFrame(rows).sort_values(["monitoring_priority_score","hx_id"],ascending=[False,True]);out["monitoring_rank"]=range(1,len(out)+1);return out

def main():
    config=json.loads((ROOT/"config/mvp_real_data_pilot.json").read_text(encoding="utf-8"));base=ROOT/"reports/tables/mvp_real_data";coverage=pd.read_csv(base/"calculation_coverage.csv",index_col=0);events=pd.read_csv(base/"signal_inferred_cleaning/signal_recovery_candidates.csv");relative=pd.read_csv(base/"empirical_relative_performance/relative_performance_timeseries.csv");relative["timestamp"]=pd.to_datetime(relative.timestamp);forecast=pd.read_csv(base/"forecast/forecast_summary.csv");priorities=build_priorities(config,coverage,events,relative,forecast);out=base/"decision_support";figdir=ROOT/"reports/figures/mvp_real_data/decision_support";out.mkdir(parents=True,exist_ok=True);figdir.mkdir(parents=True,exist_ok=True);priorities.to_csv(out/"monitoring_and_cleaning_review_priority.csv",index=False)
    scenarios=pd.DataFrame([
        {"scenario":"CONTINUE_MONITORING","status":"EXPLORATORY","action":"No inferred cleaning action","network_cit_benefit":"UNAVAILABLE","economics":"UNAVAILABLE","decision_use":"VALID CURRENT DEFAULT"},
        {"scenario":"ENGINEERING_REVIEW_SIGNAL_CANDIDATES","status":"PROVISIONAL","action":"Review E113A/E112AB signal evidence and configuration logs","network_cit_benefit":"BLOCKED","economics":"BLOCKED","decision_use":"EVIDENCE COLLECTION ONLY"},
        {"scenario":"ACQUIRE_NETWORK_AND_MAINTENANCE_INPUTS","status":"PARTIAL","action":"Resolve split/mix/bypass and maintenance evidence","network_cit_benefit":"BLOCKED_PENDING_INPUTS","economics":"BLOCKED_PENDING_INPUTS","decision_use":"UNBLOCK FUTURE COUNTERFACTUALS"},
    ]);scenarios.to_csv(out/"scenario_comparison.csv",index=False)
    pd.DataFrame([{"optimization_level":"RULE_BASED_MONITORING_RANK","status":"EXPLORATORY"},{"optimization_level":"SCENARIO_COMPARISON","status":"PARTIAL"},{"optimization_level":"GREEDY_CLEANING_SEQUENCE","status":"BLOCKED"},{"optimization_level":"CONSTRAINED_SCHEDULE_OPTIMIZATION","status":"BLOCKED"}]).to_csv(out/"optimization_readiness.csv",index=False)
    fig,ax=plt.subplots(figsize=(12,6));p=priorities.sort_values("monitoring_priority_score");ax.barh(p.hx_id,p.monitoring_priority_score);ax.set(xlabel="Evidence-based monitoring score (-)",title="Monitoring priority only - not a cleaning recommendation");fig.tight_layout();fig.savefig(figdir/"evidence_monitoring_priority.png",dpi=140);plt.close(fig);print(priorities[["hx_id","monitoring_rank","recommendation_status"]].to_string(index=False))
if __name__=="__main__":main()
