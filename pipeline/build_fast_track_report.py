"""Assemble runtime-only fast-track stage gates, coverage, blockers, and report."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/"reports/tables/mvp_real_data";FIG=ROOT/"reports/figures/mvp_real_data";OUT=BASE/"fast_track"
ALLOWED={"VALIDATED","PROVISIONAL","EXPLORATORY","PARTIAL","BLOCKED","UNAVAILABLE"}

def markdown_table(frame:pd.DataFrame)->str:
    values=frame.fillna("").astype(str);header="| "+" | ".join(values.columns)+" |";separator="| "+" | ".join(["---"]*len(values.columns))+" |";rows=["| "+" | ".join(row.str.replace("|","/",regex=False))+" |" for _,row in values.iterrows()];return "\n".join([header,separator,*rows])

def stage_gate():
    return pd.DataFrame([
        ("Raw Data","VALIDATED","Source workbook read-only; no interpolation or overwrite."),
        ("Validated Data","VALIDATED","Record-level quality and operating states retained."),
        ("HX Performance","PARTIAL","Canonical Q/LMTD/UA for 15 HX; E101G unavailable and E112C blocked."),
        ("Reference/Baseline","PROVISIONAL","Empirical references for four HX; no confirmed clean baseline."),
        ("Fouling Condition","EXPLORATORY","Relative performance only; confirmed fouling unavailable."),
        ("HX-CIT Screening","EXPLORATORY","Measured-CIT associations are non-causal screening."),
        ("Network/CIT Impact","BLOCKED","Split/mix/configuration/hot-side balances incomplete."),
        ("F101 Impact","PARTIAL","Physics duty provisional; FG calibration exploratory; fuel penalty blocked."),
        ("Forecast","EXPLORATORY","Four empirical-relative forecasts; no approved threshold."),
        ("Cleaning Recommendation","EXPLORATORY","Monitoring/review priority only; no final cleaning recommendation."),
        ("Optimization","BLOCKED","Network consequence, economics, duration, and constraints incomplete."),
    ],columns=["stage","status","basis"])

def plot_coverage():
    specs=[
      ("Data availability heatmap","A Data readiness",FIG/"01_data_availability_heatmap.png","ALL_HX","VALIDATED"),("Missing percentage","A Data readiness",FIG/"02_missing_percentage.png","ALL_HX","VALIDATED"),("Sampling interval","A Data readiness",FIG/"03_sampling_interval.png","PLANT","VALIDATED"),("Operating state timeline","A Data readiness",FIG/"05_operating_state_timeline.png","ALL_HX","VALIDATED"),("HX physics relationships","B HX physics",FIG/"coverage_completion/relationships","15_HX","VALIDATED"),("Aligned physics timelines","B HX physics",FIG/"coverage_completion/aligned_timelines","15_HX","VALIDATED"),("HX performance comparison","B HX physics",FIG/"coverage_completion/hx_performance_median_iqr.png","15_HX","VALIDATED"),("Empirical reference performance","D Reference",FIG/"empirical_relative_performance","4_HX","PROVISIONAL"),("Relative degradation","E Relative condition",FIG/"empirical_relative_performance","4_HX","EXPLORATORY"),("HX-CIT screening","F HX-CIT",FIG/"hx_cit_screening","15_HX","EXPLORATORY"),("Network validation","G Network",FIG/"network_readiness","NETWORK","BLOCKED"),("Counterfactual CIT recovery","H Counterfactual",FIG/"network_counterfactual","NETWORK","BLOCKED"),("F101 consequence","I Furnace",FIG/"f101_consequence/f101_duty_and_fuel_timeline.png","F101","PROVISIONAL"),("Forecasts","J Forecast",FIG/"forecast","4_HX","EXPLORATORY"),("Monitoring priority","K Recommendation",FIG/"decision_support/evidence_monitoring_priority.png","17_HX","EXPLORATORY"),("Scenario comparison","K Recommendation",FIG/"scenario_comparison","PORTFOLIO","BLOCKED")]
    rows=[]
    for name,stage,path,scope,intended in specs:
        if path.is_dir():files=[p for p in path.rglob("*.png") if p.stat().st_size>0]
        else:files=[path] if path.exists() and path.stat().st_size>0 else []
        status=intended if files else ("BLOCKED" if intended=="BLOCKED" else "PARTIAL")
        rows.append({"output_name":name,"stage":stage,"scope":scope,"file_path":";".join(str(p) for p in files),"status":status,"data_status":status,"valid_record_count":None,"reason_if_missing":"" if files else ("Required upstream stage is blocked." if status=="BLOCKED" else "Expected runtime plot missing or empty.")})
    return pd.DataFrame(rows)

def blockers():
    return pd.DataFrame([
      ("CONFIRMED_CLEAN_BASELINE","BLOCKED","No authoritative individual-HX maintenance/cleaning evidence."),("TAM_2021_UA_RECOVERY","BLOCKED","Crude property coverage begins 2021-04-01; pre-TAM SG unavailable."),("E101G_PERFORMANCE","UNAVAILABLE","Required raw tags missing."),("E112C_PERFORMANCE","BLOCKED","Topology and terminal-temperature conflict."),("QHOT_AND_ENERGY_CLOSURE","UNAVAILABLE","No credible hot flow/Cp/density mapping."),("HX_DIFFERENTIAL_PRESSURE","UNAVAILABLE","No confirmed inlet/outlet pressure pairs."),("FULL_NETWORK_MODEL","BLOCKED","Split/mix fractions, configuration states, and hot-side balances incomplete."),("NETWORK_COUNTERFACTUAL_CIT","BLOCKED","Full temperature propagation not validated."),("FUEL_PENALTY_ECONOMICS","BLOCKED","Approved fuel LHV, efficiency, dated price, and cleaning costs incomplete."),("FORECAST_THRESHOLD_DATE","BLOCKED","No approved relative-performance threshold."),("FINAL_CLEANING_RECOMMENDATION","BLOCKED","Network consequence, economics, and confirmed event evidence incomplete."),("SCHEDULE_OPTIMIZATION","BLOCKED","Duration, workforce, isolation, budget, and validated benefits incomplete."),
    ],columns=["output","status","blocker"])

def main():
    OUT.mkdir(parents=True,exist_ok=True);stages=stage_gate();plots=plot_coverage();blocks=blockers();assert set(stages.status)<=ALLOWED;stages.to_csv(OUT/"end_to_end_stage_gate.csv",index=False);plots.to_csv(OUT/"plot_coverage_matrix.csv",index=False);blocks.to_csv(OUT/"blocker_register.csv",index=False)
    copies={"hx_data_readiness_matrix.csv":BASE/"coverage_completion/data_quality_summary.csv","hx_performance_summary.csv":BASE/"coverage_completion/hx_performance_summary.csv","baseline_reference_summary.csv":BASE/"empirical_relative_performance/exploratory_summary.csv","hx_cit_screening.csv":BASE/"hx_cit_screening/hx_cit_relationships.csv","network_readiness.csv":BASE/"network_readiness/network_readiness_by_hx.csv","f101_consequence_summary.csv":BASE/"f101_consequence/f101_consequence_summary.csv","forecast_summary.csv":BASE/"forecast/forecast_summary.csv","cleaning_priority.csv":BASE/"decision_support/monitoring_and_cleaning_review_priority.csv","scenario_comparison.csv":BASE/"decision_support/scenario_comparison.csv"}
    for name,source in copies.items():shutil.copyfile(source,OUT/name)
    ref=pd.read_csv(BASE/"empirical_relative_performance/exploratory_summary.csv");condition=ref[["hx_id","reference_ua_empirical","relative_ua_empirical_min","relative_ua_empirical_max","relative_performance_loss_min","relative_performance_loss_max","empirical_reference_confidence","clean_condition_confirmed"]].copy();condition["status"]="EXPLORATORY";condition["interpretation"]="Relative condition against empirical high-performance reference; not confirmed fouling.";condition.to_csv(OUT/"relative_condition_summary.csv",index=False)
    report=f"""# CPHT-F101 Fast-Track Executive Engineering Report\n\nGenerated from runtime plant data. Raw data were not modified.\n\n## Plant-evidence conclusions\n\n- Two plant-level low-total-charge TAM intervals were detected in 2021 and 2024.\n- Canonical steady-state Q, LMTD, and UA are available for 15 mapped HX.\n- No individual HX cleaning event or confirmed clean condition is established.\n\n## Provisional findings\n\n- Four HX use empirical high-performance references, not clean baselines.\n- F101 physics duty uses measured CIT/COT and calculated mass flow/Cp.\n\n## Model-dependent exploratory findings\n\n- HX-CIT correlations, FG calibration, forecasts, and monitoring ranks are screening outputs only.\n- None constitutes causal cleaning benefit or a final cleaning recommendation.\n\n## Unavailable conclusions\n\n- Full-network CIT recovery, fuel/economic benefit, and schedule optimization remain blocked.\n- Confirmed fouling index remains unavailable without confirmed clean evidence.\n\n## Stage gates\n\n{markdown_table(stages)}\n\n## Blockers\n\n{markdown_table(blocks)}\n""";(OUT/"executive_engineering_report.md").write_text(report,encoding="utf-8");print(stages.to_string(index=False))
if __name__=="__main__":main()
