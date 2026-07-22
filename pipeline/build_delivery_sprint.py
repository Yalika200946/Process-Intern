"""Assemble an honest, generation-consistent end-to-end delivery sprint package."""
from __future__ import annotations
import hashlib,json,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/"reports/tables/mvp_real_data";OUT=BASE/"delivery_sprint";SNAP=OUT/"dashboard_snapshot"
ALLOWED={"VALIDATED","PROVISIONAL","EXPLORATORY","PARTIAL","BLOCKED","UNAVAILABLE"}
def read(path):return pd.read_csv(path)
def write(frame,name):assert set(frame.status.dropna())<=ALLOWED if "status" in frame else True;frame.to_csv(OUT/name,index=False)

def main():
    OUT.mkdir(parents=True,exist_ok=True);SNAP.mkdir(parents=True,exist_ok=True)
    mix=read(BASE/"cpht2_mix_validation/mix_temperature_metrics.csv");gates=read(BASE/"cpht2_mix_validation/network_gates.csv");network=json.loads((BASE/"cpht2_mix_validation/network_status.json").read_text())
    physics=read(BASE/"critical_correction/corrected_hx_performance_summary.csv");monitor=read(BASE/"decision_support/monitoring_and_cleaning_review_priority.csv")
    stages=pd.DataFrame([
      ("Raw Data","VALIDATED","Read-only source and canonical adapter"),("Validated Data","VALIDATED","Quality and operating masks"),("HX Performance","PROVISIONAL","Q/LMTD validated; apparent UA uses unapproved F"),("Empirical Reference","PROVISIONAL","Four historical high-performance references"),("Fouling Condition","EXPLORATORY","Relative performance is not confirmed fouling"),("HX-CIT Screening","EXPLORATORY","Association only"),("CPHT-2 Pilot Network","PARTIAL","Flow/continuity provisional; mix and propagation thresholds required"),("Pilot Counterfactual CIT","BLOCKED","Pilot network gate not open"),("F101 Consequence","PROVISIONAL","Physics duty; attributable fuel saving blocked"),("Forecast","EXPLORATORY","Chronological benchmark; no approved action threshold"),("Monitoring Decision","EXPLORATORY","Monitoring priority only"),("Dashboard Snapshot","VALIDATED","Generation-consistent evidence-labeled snapshot"),("Optimization","BLOCKED","Outside sprint and missing validated consequences")],columns=["stage","status","basis"]);write(stages,"end_to_end_stage_table.csv")
    hx=physics.rename(columns={"valid_coverage_pct":"valid_data_coverage_pct"});hx["status"]="PROVISIONAL";hx["usable_for_dashboard"]=True;hx["plant_decision_ready"]=False;write(hx,"hx_by_hx_coverage.csv")
    equations=pd.DataFrame([
      ("mass_flow","m=volumetric_flow*density/3600","kg/s","VALIDATED","Canonical tested"),("Qcold","m*Cp*(Tout-Tin)","kW","VALIDATED","Canonical tested"),("LMTD","(dT1-dT2)/ln(dT1/dT2)","degC","VALIDATED","Canonical tested"),("apparent_UA","Q/(F*LMTD)","kW/K","PROVISIONAL","F=1 screening assumption"),("U","UA/verified area","W/m2/K","BLOCKED","No transferable approved group area/F"),("mix_temperature","sum(m*Cp*T)/sum(m*Cp)","degC","PROVISIONAL","Measured-node closure threshold required"),("F101_duty","m*Cp*(COT-CIT)","kW","PROVISIONAL","Fuel attribution blocked")],columns=["quantity","equation","unit","status","basis"]);write(equations,"equation_unit_audit.csv")
    shutil.copyfile(BASE/"critical_correction/area_f_factor_audit.csv",OUT/"area_f_factor_audit.csv")
    shutil.copyfile(BASE/"cpht2_mix_validation/pilot_network_validation_metrics.csv",OUT/"cpht2_pilot_validation.csv")
    counter=pd.DataFrame([{"scope":"PILOT_SINGLE_HX","status":"BLOCKED","reason":"Gates B and E require engineering error thresholds; no restoration counterfactual executed.","network_status":network["network_status"],"cit_recovery_c":None,"compensation_ratio":None}]);write(counter,"pilot_counterfactual_blocker.csv")
    shutil.copyfile(BASE/"f101_consequence/f101_consequence_summary.csv",OUT/"furnace_estimate.csv")
    forecast=read(BASE/"forecast/forecast_summary.csv");leader=[]
    for r in forecast.to_dict("records"):leader.append({"scope":r.get("hx_id"),"model":"RECENT_LINEAR_TREND","validation":"chronological_holdout","metric":r.get("linear_rmse"),"benchmark":r.get("persistence_rmse"),"status":"EXPLORATORY","selected":bool(pd.notna(r.get("linear_rmse")) and r.get("linear_rmse")<r.get("persistence_rmse"))})
    for r in read(BASE/"cpht2_mix_validation/pilot_network_validation_metrics.csv").to_dict("records"):leader.append({"scope":r.get("node"),"model":"RIDGE_SEMI_EMPIRICAL_PROPAGATION","validation":r.get("validation_method"),"metric":r.get("rmse_c"),"benchmark":None,"status":"PARTIAL","selected":False})
    write(pd.DataFrame(leader),"model_leaderboard.csv");shutil.copyfile(BASE/"forecast/forecast_summary.csv",OUT/"forecast_benchmark.csv");shutil.copyfile(BASE/"decision_support/monitoring_and_cleaning_review_priority.csv",OUT/"monitoring_priority.csv")
    dashboard=pd.DataFrame([("A Data Quality","VALIDATED","availability; missingness; flatline; operating state; valid coverage","None"),("B HX Performance","PROVISIONAL","temperatures; Q; LMTD; apparent UA; warnings","Verified U unavailable"),("C Experimental Analytics","EXPLORATORY","empirical reference; relative performance; HX-CIT screening; pilot; furnace; forecast","Permanent non-action banner required"),("D Cleaning Decision","BLOCKED","None","No confirmed condition/network benefit/economics")],columns=["dashboard_level","status","allowed_visualizations","prohibited_or_blocked"]);write(dashboard,"dashboard_readiness_report.csv")
    blockers=pd.DataFrame([("VERIFIED_U","BLOCKED","Approved transferable area and F"),("CONFIRMED_FOULING","BLOCKED","Maintenance/clean-state evidence"),("PILOT_COUNTERFACTUAL_CIT","BLOCKED","Acceptable mix and propagation error thresholds"),("FULL_NETWORK_CIT","BLOCKED","Pilot gate plus time-varying residue lineup"),("HX_FUEL_SAVING","BLOCKED","Network attribution and approved LHV/efficiency"),("FINAL_CLEANING_PRIORITY","BLOCKED","Confirmed condition/consequence/feasibility/economics"),("OPTIMIZATION","BLOCKED","Outside sprint; operational constraints incomplete")],columns=["capability","status","smallest_missing_input"]);write(blockers,"blocker_register.csv")
    score=pd.DataFrame([("Data ingestion and quality",15,15,"VALIDATED"),("Canonical thermal equations",15,13,"PROVISIONAL"),("Topology/configuration evidence",15,11,"PROVISIONAL"),("HX performance coverage",15,12,"PROVISIONAL"),("Pilot network validation",15,7,"PARTIAL"),("Consequence and forecast",10,5,"EXPLORATORY"),("Decision traceability",10,6,"EXPLORATORY"),("Reproducibility and tests",5,5,"VALIDATED")],columns=["dimension","max_score","achieved_score","status"]);write(score,"engineering_scorecard.csv")
    maturity=pd.DataFrame([{"status":"PROVISIONAL","engineering_score":int(score.achieved_score.sum()),"score_max":100,"project_maturity_level":"LEVEL_4_ENGINEERING_ANALYTICAL_PROTOTYPE","highest_honest_dashboard_level":"LEVEL_C_EXPERIMENTAL_ANALYTICS","plant_action_ready":False}]);write(maturity,"project_maturity.csv")
    generation_id="sprint-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");banner="PROVISIONAL / EXPLORATORY - NOT FOR DIRECT PLANT ACTION"
    payloads={"data_quality":{"status":"VALIDATED","source":"coverage_completion"},"hx_performance":{"status":"PROVISIONAL","records":hx.to_dict("records")},"experimental_analytics":{"status":"EXPLORATORY","banner":banner,"network_status":network,"mix_metrics":mix.to_dict("records"),"gates":gates.to_dict("records")}}
    hashes={}
    for name,payload in payloads.items():
        body={"generation_id":generation_id,"generated_at":datetime.now(timezone.utc).isoformat(),"schema_version":"1.0.0",**payload};path=SNAP/f"{name}.json";path.write_text(json.dumps(body,indent=2,default=str),encoding="utf-8");hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    (SNAP/"manifest.json").write_text(json.dumps({"generation_id":generation_id,"banner":banner,"artifacts":hashes,"status":"VALIDATED","prohibited_claims":["confirmed fouling","counterfactual CIT recovery","guaranteed fuel saving","final cleaning action","ROI"]},indent=2),encoding="utf-8")
    commit=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,capture_output=True,text=True).stdout.strip()
    report=f"# CPHT-F101 Delivery Sprint\n\nCanonical command: `python pipeline/run_fast_track_end_to_end.py`\n\nCommit at generation: `{commit}`\n\nEngineering score: **{score.achieved_score.sum()}/100**\n\nMaturity: **LEVEL_4_ENGINEERING_ANALYTICAL_PROTOTYPE**\n\nPilot network: **{network['network_status']}**\n\nCounterfactual CIT: **BLOCKED**\n"
    (OUT/"delivery_sprint_report.md").write_text(report,encoding="utf-8")
    print(stages.to_string(index=False));print(maturity.to_string(index=False))
if __name__=="__main__":main()
