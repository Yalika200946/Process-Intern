"""Close the Batch-5 full-network gate from explicit evidence, never inference alone."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/tables/mvp_real_data"
OUT = BASE / "full_engineering_program/batch_05"


def network_hard_gate_status(gates: pd.DataFrame) -> dict:
    required = set(gates.gate)
    mandatory = {"CPHT2_FLOW_CLOSURE", "CPHT2_MIX_CLOSURE", "ALL_BRANCH_PROPAGATION",
                 "TERMINAL_CONFIGURATION", "MEASURED_CIT_REPRODUCTION"}
    missing = sorted(mandatory - required)
    failed = gates.loc[gates.gate.isin(mandatory) & gates.status.ne("VALIDATED"), "gate"].tolist()
    ready = not missing and not failed
    return {"network_status":"VALIDATED" if ready else "BLOCKED",
            "network_complete":ready, "missing_gates":missing, "failed_or_provisional_gates":failed}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mix = pd.read_csv(BASE / "cpht2_mix_validation/mix_temperature_metrics.csv")
    mix_all = mix[mix.scope.eq("ALL_VALID")].iloc[0]
    pilot = pd.read_csv(BASE / "cpht2_mix_validation/pilot_network_validation_metrics.csv")
    config = pd.read_csv(BASE / "configuration_states/configuration_validation_summary.csv").iloc[0]
    gates = pd.DataFrame([
        {"gate":"CPHT2_FLOW_CLOSURE","status":"PROVISIONAL","valid_records":2008,
         "metric":float(config.cpht2_balance_within_tolerance_pct),"unit":"percent within provisional tolerance","blocker":"FLOW_TOLERANCE_NOT_PLANT_VALIDATED"},
        {"gate":"CPHT2_MIX_CLOSURE","status":"PROVISIONAL","valid_records":int(mix_all.valid_record_count),
         "metric":float(mix_all.MAE_C),"unit":"MAE degC","blocker":"PROVISIONAL_THRESHOLD_ONLY"},
        {"gate":"BRANCH_1FI015_PROPAGATION","status":"PROVISIONAL","valid_records":int(pilot.valid_test_cases.min()),
         "metric":float(pilot.rmse_c.max()),"unit":"maximum node RMSE degC","blocker":"PILOT_STOPS_AT_E104_OUT"},
        {"gate":"ALL_BRANCH_PROPAGATION","status":"BLOCKED","valid_records":0,"metric":None,"unit":"degC",
         "blocker":"BRANCH_1FI016_AND_1FI017_MODELS_NOT_CHRONOLOGICALLY_VALIDATED;E105AB_COUNTERFACTUAL_MODEL_MISSING"},
        {"gate":"TERMINAL_CONFIGURATION","status":"BLOCKED","valid_records":0,"metric":None,"unit":"state",
         "blocker":"NO_VALVE_HISTORY;E112C_DIRECT_DATA_UNAVAILABLE;E113A_E112C_ACTIVE_LINEUP_UNKNOWN"},
        {"gate":"MEASURED_CIT_REPRODUCTION","status":"BLOCKED","valid_records":0,"metric":None,"unit":"degC",
         "blocker":"NO_CONFIGURATION_AWARE_PROPAGATION_TO_1TI116"},
    ])
    decision = network_hard_gate_status(gates)
    gates.to_csv(OUT / "network_validation_registry.csv", index=False)
    blockers = pd.DataFrame([
        {"blocker_id":"NET-E105AB-MODEL","required_input":"Resolve 1TI196 hot-in identity and validate E105AB counterfactual temperature response","decision_impact":"Completes branch 1FI015 beyond E104"},
        {"blocker_id":"NET-RESIDUE-LINEUP","required_input":"Timestamped E113A/E112C active, bypass, cleaning, or valve state","decision_impact":"Selects terminal topology per timestamp"},
        {"blocker_id":"NET-E112C-DATA","required_input":"E112C crude inlet/outlet and active-flow evidence, or an approved substitution model","decision_impact":"Models alternate terminal operation"},
        {"blocker_id":"NET-CIT-CLOSURE","required_input":"Chronological reproduction of measured 1TI116 across operating configurations","decision_impact":"Opens network counterfactual CIT"},
    ])
    blockers.to_csv(OUT / "network_engineering_input_request.csv", index=False)
    payload = {"batch":5, **decision, "pilot_branch_status":"PROVISIONAL",
               "full_network_cit_counterfactual_allowed":False,
               "single_hx_network_recovery_allowed":False,
               "multi_hx_interaction_allowed":False}
    (OUT / "batch_05_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
