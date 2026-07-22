"""Run E104 pilot-endpoint restoration; explicitly block full CIT attribution."""
from __future__ import annotations
import json,sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.network.validation import pilot_endpoint_counterfactual
BASE=ROOT/"reports/tables/mvp_real_data";OUT=BASE/"pilot_counterfactual"
def main():
    OUT.mkdir(parents=True,exist_ok=True);network=json.loads((BASE/"cpht2_mix_validation/network_status.json").read_text())
    if not network["counterfactual_cit_can_start"]:raise RuntimeError("Pilot gates are not open")
    refs=pd.read_csv(BASE/"empirical_relative_performance/exploratory_summary.csv");reference=float(refs.loc[refs.hx_id.eq("E104"),"reference_ua_empirical"].iloc[0])
    p=pd.read_csv(BASE/"hx_physics_validation.csv",parse_dates=["timestamp"]);g=p[p.hx_id.eq("E104")&p.operating_valid.astype(bool)&p.ua_valid.astype(bool)].copy();rows=[]
    for r in g.itertuples():
        calc=pilot_endpoint_counterfactual(r.q_cold_value,r.ua_value,reference,r.lmtd_value,r.mass_flow_value,r.cp_kj_kg_k)
        rows.append({"timestamp":r.timestamp,"hx_id":"E104","reference_ua_empirical_kw_k":reference,"reference_status":"EMPIRICAL_HIGH_PERFORMANCE_REFERENCE","clean_state_confirmed":False,"cleaning_event_confirmed":False,**calc,"result_status":"EXPLORATORY","network_scope":"E103AB_E104_PILOT_ENDPOINT","full_cit_recovery_available":False,"network_effects_included":False})
    out=pd.DataFrame(rows);out.to_csv(OUT/"e104_pilot_endpoint_counterfactual.csv",index=False)
    recent=out.tail(180);summary=pd.DataFrame([{"hx_id":"E104","status":"EXPLORATORY","valid_records":int(out.is_valid.sum()),"reference_ua_empirical_kw_k":reference,"median_pilot_endpoint_gain_c_recent":recent.pilot_endpoint_temperature_gain_c.median(),"p90_pilot_endpoint_gain_c_recent":recent.pilot_endpoint_temperature_gain_c.quantile(.9),"pilot_endpoint":"E104_OUT","cit_recovery_status":"BLOCKED","cit_blocker":"E105AB_AND_TERMINAL_TO_CIT_PROPAGATION_NOT_VALIDATED","compensation_ratio_status":"UNAVAILABLE","interpretation":"Counterfactual thermal recovery at E104 outlet only; not CIT recovery."}]);summary.to_csv(OUT/"pilot_counterfactual_summary.csv",index=False)
    pd.DataFrame([{"status":"BLOCKED","output":"PILOT_COUNTERFACTUAL_CIT","reason":"Validated pilot ends at E104 outlet. E105AB and terminal E113A/E112C propagation to measured CIT are not validated.","smallest_next_step":"Validate E105AB mapping/propagation, then propagate branch outlet through accepted mix and terminal section."}]).to_csv(OUT/"counterfactual_cit_blocker.csv",index=False)
    print(summary.to_string(index=False))
if __name__=="__main__":main()
