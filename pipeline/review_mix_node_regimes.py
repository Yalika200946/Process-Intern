"""Review 1TI115 measurement regimes and propose, but never approve, error gates."""
from __future__ import annotations
from pathlib import Path
import sys
import matplotlib.pyplot as plt
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.network.validation import classify_mix_node_regime,screening_threshold_proposal
BASE=ROOT/"reports/tables/mvp_real_data";OUT=BASE/"mix_node_regime_review";FIG=ROOT/"reports/figures/mvp_real_data/mix_node_regime_review"

def main():
    OUT.mkdir(parents=True,exist_ok=True);FIG.mkdir(parents=True,exist_ok=True)
    mix=pd.read_csv(BASE/"cpht2_mix_validation/mix_temperature_closure.csv",parse_dates=["timestamp"])
    mix["mix_node_regime"]=[classify_mix_node_regime(r.mix_measured_c,r.inlet_min_c,r.inlet_max_c) for r in mix.itertuples()]
    mix["mix_node_eligible"]=mix.mix_node_regime.eq("MIX_NODE_PHYSICALLY_CONSISTENT")
    mix["eligibility_status"]="PROVISIONAL_CONFIGURATION_SCREENING"
    mix["raw_value_preserved"]=True
    change=mix.mix_node_regime.ne(mix.mix_node_regime.shift()).cumsum()
    periods=mix.groupby(change).agg(regime=("mix_node_regime","first"),start=("timestamp","min"),end=("timestamp","max"),records=("timestamp","size"),median_1ti115_c=("mix_measured_c","median"),median_predicted_mix_c=("mix_predicted_c","median")).reset_index(drop=True)
    mix["year"]=mix.timestamp.dt.year
    yearly=mix.groupby("year").agg(records=("timestamp","size"),eligible_records=("mix_node_eligible","sum"),median_1ti115_c=("mix_measured_c","median"),median_predicted_mix_c=("mix_predicted_c","median")).reset_index();yearly["eligible_pct"]=100*yearly.eligible_records/yearly.records;yearly["status"]="PROVISIONAL"
    valid=mix[mix.closure_valid.astype(bool)]
    proposal=screening_threshold_proposal(valid.residual_C)
    threshold=pd.DataFrame([{"metric":"mix_temperature_closure","status":"PROVISIONAL",**proposal,"interpretation":"Suggested review gate only; not plant-approved and does not open counterfactual CIT."},{"metric":"pilot_intermediate_node","status":"PROVISIONAL","proposed_mae_limit_c":5.0,"proposed_absolute_bias_limit_c":5.0,"proposed_p90_limit_c":None,"approval_status":"ENGINEERING_REVIEW_REQUIRED","interpretation":"Review proposal based on current pilot scale."},{"metric":"pilot_branch_outlet","status":"PROVISIONAL","proposed_mae_limit_c":10.0,"proposed_absolute_bias_limit_c":10.0,"proposed_p90_limit_c":None,"approval_status":"ENGINEERING_REVIEW_REQUIRED","interpretation":"Review proposal based on current pilot scale."}])
    evidence=mix[["timestamp","mix_measured_c","mix_predicted_c","inlet_min_c","inlet_max_c","mix_node_regime","mix_node_eligible","closure_valid","warning_code","raw_value_preserved"]].copy();evidence["residue_lineup_evidence"]="NO_VALVE_HISTORY";evidence["network_use_status"]=evidence.mix_node_eligible.map({True:"ELIGIBLE_FOR_PROVISIONAL_MIX_REVIEW",False:"EXCLUDED_CONFIGURATION_OR_SENSOR_REGIME"})
    mix.to_csv(OUT/"mix_node_regime_timeline.csv",index=False);periods.to_csv(OUT/"mix_node_regime_periods.csv",index=False);yearly.to_csv(OUT/"mix_node_regime_by_year.csv",index=False);threshold.to_csv(OUT/"engineering_threshold_proposal.csv",index=False);evidence.to_csv(OUT/"residue_mix_eligibility_timeline.csv",index=False)
    fig,ax=plt.subplots(figsize=(15,5));ax.plot(mix.timestamp,mix.mix_measured_c,label="1TI115 measured",lw=.7);ax.plot(mix.timestamp,mix.mix_predicted_c,label="Predicted branch mix",lw=.7);bad=~mix.mix_node_eligible;ax.scatter(mix.loc[bad,"timestamp"],mix.loc[bad,"mix_measured_c"],s=5,color="red",label="Excluded regime");ax.set(xlabel="Time",ylabel="Temperature (degC)",title="1TI115 measurement-regime review");ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(FIG/"1ti115_regime_timeline.png",dpi=140);plt.close(fig)
    print(yearly.to_string(index=False));print(threshold.to_string(index=False))
if __name__=="__main__":main()
