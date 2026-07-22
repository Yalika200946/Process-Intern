"""Largest credible network-readiness audit without inventing topology."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]

def tag_set(definition,aliases):
    if isinstance(definition,str):return {aliases.get(definition,definition).casefold()}
    return {aliases.get(tag,tag).casefold() for tag in definition.get("tags",[])}

def infer_confirmed_tag_edges(config:dict)->pd.DataFrame:
    aliases=config.get("aliases",{});hxs=config["heat_exchangers"];rows=[]
    for upstream,u in hxs.items():
        if u.get("status") in {"BLOCKED","UNAVAILABLE"}:continue
        out=tag_set(u["cold_out"],aliases)
        for downstream,d in hxs.items():
            if upstream==downstream or d.get("status") in {"BLOCKED","UNAVAILABLE"}:continue
            shared=out & tag_set(d["cold_in"],aliases)
            if shared:rows.append({"upstream_hx":upstream,"downstream_hx":downstream,"shared_temperature_tag":"|".join(sorted(shared)),"edge_status":"VALIDATED_TAG_CONTINUITY","temperature_continuity_basis":"SAME_MEASURED_TAG","network_sequence_complete":False})
    return pd.DataFrame(rows)

def readiness(config:dict,edges:pd.DataFrame)->pd.DataFrame:
    rows=[]
    for hx_id,hx in config["heat_exchangers"].items():
        status=hx.get("status")
        if status in {"BLOCKED","UNAVAILABLE"}:output="BLOCKED" if status=="BLOCKED" else "UNAVAILABLE";reason=hx.get("blocked_reason",hx.get("unavailable_reason"))
        else:
            linked=not edges[(edges.upstream_hx==hx_id)|(edges.downstream_hx==hx_id)].empty
            output="PARTIAL" if linked else "BLOCKED";reason="SERIAL_TAG_EDGE_KNOWN_BUT_SPLIT_MIX_AND_HOT_SIDE_BALANCE_INCOMPLETE" if linked else "NO_CONFIRMED_CONNECTION_TO_CIT_NETWORK"
        rows.append({"hx_id":hx_id,"network_readiness_status":output,"reason":reason,"sequence_known":bool(not edges[(edges.upstream_hx==hx_id)|(edges.downstream_hx==hx_id)].empty) if not edges.empty else False,"split_fraction_known":False,"mixing_balance_validated":False,"bypass_state_timeseries_available":False,"hot_side_balance_available":False,"single_hx_counterfactual_status":"BLOCKED","counterfactual_blocker":"FULL_TEMPERATURE_PROPAGATION_NOT_VALIDATED"})
    return pd.DataFrame(rows)

def main():
    config=json.loads((ROOT/"config/mvp_real_data_pilot.json").read_text(encoding="utf-8"));edges=infer_confirmed_tag_edges(config);ready=readiness(config,edges);out=ROOT/"reports/tables/mvp_real_data/network_readiness";out.mkdir(parents=True,exist_ok=True);edges.to_csv(out/"validated_tag_continuity_edges.csv",index=False);ready.to_csv(out/"network_readiness_by_hx.csv",index=False)
    pd.DataFrame([{"network_scope":"CPHT_FULL_NETWORK","status":"BLOCKED","validated_serial_edge_count":len(edges),"predicted_vs_measured_cit_status":"BLOCKED","counterfactual_cit_recovery_status":"BLOCKED","reason":"Split/mix fractions, configuration states, and hot-side balances are incomplete; local equivalent gains must not be summed."}]).to_csv(out/"network_validation_summary.csv",index=False)
    print(ready.network_readiness_status.value_counts().to_string())
if __name__=="__main__":main()
