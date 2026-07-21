"""Fit, validate and export the 16-HX hybrid dual-track network model."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.network.datasheet import read_datasheet_diagnostics
from src.network.hybrid import ALL_HX, counterfactuals, fit_empirical_models, simulate_cpht2

DATA = Path(os.environ.get("CPHT_DATA_DIR", r"C:\Desktop\Bangchak Internship 2026\Data"))
DASH = ROOT / "dashboard" / "data"
FIG = ROOT / "figures" / "hybrid_network"


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / name, parse_dates=["Timestamp"]).set_index("Timestamp").sort_index()


def _validate_network(process, features, states, models, max_rows=365):
    idx = process.index.intersection(features.index).intersection(states.index)
    idx = idx[process.loc[idx, "1TI116.pv"].notna()][-max_rows:]
    rows = []
    for ts in idx:
        result = simulate_cpht2(process.loc[ts], features.loc[ts], states.loc[ts], models)
        if result.get("cit") is not None:
            rows.append({"timestamp": ts, "measured": float(process.at[ts, "1TI116.pv"]), "simulated": result["cit"]})
    frame = pd.DataFrame(rows).set_index("timestamp") if rows else pd.DataFrame(columns=["measured", "simulated"])
    if frame.empty:
        return frame, {"passed": False, "reason": "NO_VALIDATION_ROWS"}
    mae = float(np.mean(np.abs(frame.measured - frame.simulated)))
    persistence = frame.measured.shift(1)
    persistence_mae = float(np.mean(np.abs(frame.measured.iloc[1:] - persistence.iloc[1:])))
    bias = float(np.mean(frame.simulated - frame.measured))
    passed = len(frame) >= 90 and mae <= 1.0
    return frame, {"n": len(frame), "mae_c": round(mae, 4), "persistence_mae_c": round(persistence_mae, 4),
                   "bias_c": round(bias, 4), "passed": passed,
                   "criteria": "topology/energy-path reconstruction: n>=90 and MAE<=1C; persistence shown only as context"}


def _validate_events(process, features, states, models):
    source = DATA / "Cleaning_Impact_Summary.csv"
    if not source.exists():
        return [], {"passed": False, "reason": "NO_CLEANING_IMPACT_SUMMARY"}
    events = pd.read_csv(source, parse_dates=["event_date"])
    rows = []
    for event in events.itertuples(index=False):
        hx = str(event.HX)
        measured = getattr(event, "dCIT", np.nan)
        if hx not in models or not np.isfinite(measured) or measured <= 0:
            continue
        candidates = process.index[process.index < pd.Timestamp(event.event_date)]
        if candidates.empty:
            continue
        ts = candidates[-1]
        singles, _ = counterfactuals(process.loc[ts], features.loc[ts], states.loc[ts], models)
        predicted = next((r["cit_recovery_c"] for r in singles if r["HX"] == hx), None)
        if predicted is not None:
            rows.append({"HX": hx, "event_date": str(pd.Timestamp(event.event_date).date()),
                         "predicted_cit_recovery_c": predicted, "measured_cit_recovery_c": round(float(measured), 4),
                         "error_c": round(predicted - float(measured), 4)})
    if not rows:
        return [], {"passed": False, "reason": "NO_ELIGIBLE_CONFIRMED_EVENTS"}
    errors = np.asarray([r["error_c"] for r in rows])
    metrics = {"n": len(rows), "mae_c": round(float(np.mean(np.abs(errors))), 4),
               "bias_c": round(float(np.mean(errors)), 4),
               "passed": len(rows) >= 5 and float(np.mean(np.abs(errors))) <= 2.5,
               "criteria": "n>=5 eligible events and MAE<=2.5C"}
    return rows, metrics


def _plots(validation, model_rows, singles, datasheet, latest_network):
    FIG.mkdir(parents=True, exist_ok=True); paths = []
    fig, ax = plt.subplots(figsize=(11, 5)); ax.plot(validation.index, validation.measured, label="Measured CIT", lw=1.5); ax.plot(validation.index, validation.simulated, label="Hybrid simulated CIT", lw=1.2); ax.set(title="Measured vs hybrid-network CIT", ylabel="°C"); ax.legend(); ax.grid(alpha=.25)
    p=FIG/"actual_vs_simulated_cit.png"; fig.tight_layout(); fig.savefig(p,dpi=160); plt.close(fig); paths.append(str(p.relative_to(ROOT)))

    fig, ax = plt.subplots(figsize=(10, 6)); ordered=sorted(model_rows,key=lambda r:(r["mae_c"] is None,r["mae_c"] or 999)); ax.barh([r["HX"] for r in ordered],[r["mae_c"] or 0 for r in ordered],color=["#2a9d8f" if r["accepted"] else "#e9c46a" for r in ordered]); ax.set(title="Empirical clean ΔT model validation",xlabel="Chronological MAE (°C)")
    p=FIG/"hx_model_mae.png"; fig.tight_layout(); fig.savefig(p,dpi=160); plt.close(fig); paths.append(str(p.relative_to(ROOT)))

    ranked=sorted([r for r in singles if r["cit_recovery_c"] is not None],key=lambda r:r["cit_recovery_c"],reverse=True); fig,ax=plt.subplots(figsize=(10,5)); ax.bar([r["HX"] for r in ranked],[r["cit_recovery_c"] for r in ranked],color="#457b9d"); ax.tick_params(axis="x",rotation=55); ax.set(title="Hybrid clean-one-HX counterfactual",ylabel="CIT recovery (°C)")
    p=FIG/"counterfactual_cit_recovery.png"; fig.tight_layout(); fig.savefig(p,dpi=160); plt.close(fig); paths.append(str(p.relative_to(ROOT)))

    fig,ax=plt.subplots(figsize=(10,5)); hx=ALL_HX; empirical=[1 if next(r for r in model_rows if r["HX"]==h)["status"] not in {"INSUFFICIENT","INFERRED_ONLY","INSUFFICIENT_CLEAN_ROWS"} else 0 for h in hx]; design=[1 if datasheet.get(h,{}).get("coverage")=="AVAILABLE" else 0 for h in hx]; x=np.arange(len(hx)); ax.bar(x-.2,empirical,.4,label="Empirical"); ax.bar(x+.2,design,.4,label="Usable datasheet"); ax.set_xticks(x,hx,rotation=55); ax.set_yticks([0,1],["No","Yes"]); ax.set(title="Model/data coverage by HX"); ax.legend()
    p=FIG/"model_coverage.png"; fig.tight_layout(); fig.savefig(p,dpi=160); plt.close(fig); paths.append(str(p.relative_to(ROOT)))

    fig,ax=plt.subplots(figsize=(10,5)); duty=[datasheet.get(h,{}).get("diagnostic_clean_duty_kw") for h in hx]; keep=[(h,v) for h,v in zip(hx,duty) if v is not None]; ax.bar([h for h,_ in keep],[v/1000 for _,v in keep],color="#8d99ae"); ax.set(title="Datasheet clean-duty diagnostic (partial coverage)",ylabel="MW design reference"); ax.tick_params(axis="x",rotation=50)
    p=FIG/"datasheet_clean_duty.png"; fig.tight_layout(); fig.savefig(p,dpi=160); plt.close(fig); paths.append(str(p.relative_to(ROOT)))

    fig,ax=plt.subplots(figsize=(11,6)); branch_names=[]; outlets=[]
    for name,b in latest_network.get("branches",{}).items(): branch_names.append(name); outlets.append(b["outlet_c"])
    ax.bar(branch_names,outlets,color="#52b788"); ax.axhline(latest_network.get("mixed_c",0),ls="--",color="#e76f51",label="Mixed temperature"); ax.axhline(latest_network.get("cit",0),ls=":",color="#264653",label="Simulated CIT"); ax.set(title="Latest CPHT-2 branch temperature propagation",ylabel="°C"); ax.legend()
    p=FIG/"latest_temperature_profile.png"; fig.tight_layout(); fig.savefig(p,dpi=160); plt.close(fig); paths.append(str(p.relative_to(ROOT)))
    return paths


def main():
    process=_read("Process_information_cleaned.csv"); features=_read("Feature_calculated.csv"); states=_read("Operating_State.csv")
    common=process.index.intersection(features.index).intersection(states.index); process=process.loc[common]; features=features.loc[common]; states=states.loc[common]
    models=fit_empirical_models(process,features,states)
    model_rows=[{"HX":hx,"status":m.status,"accepted":m.accepted,"n_train":m.n_train,"n_test":m.n_test,
                 "mae_c":None if m.mae_c is None else round(m.mae_c,4),"baseline_mae_c":None if m.baseline_mae_c is None else round(m.baseline_mae_c,4),
                 "algorithm":m.algorithm,"feature_tags":list(m.feature_tags)} for hx,m in models.items()]
    validation,metrics=_validate_network(process,features,states,models)
    event_rows,event_metrics=_validate_events(process,features,states,models)
    latest=common[-1]; latest_network=simulate_cpht2(process.loc[latest],features.loc[latest],states.loc[latest],models)
    singles,interactions=counterfactuals(process.loc[latest],features.loc[latest],states.loc[latest],models)
    datasheet=read_datasheet_diagnostics(DATA/"Data Sheet Heat Exchanger.xlsx")
    accepted_positions=sum(1 for m in models.values() if m.accepted)
    overall_pass=bool(metrics.get("passed") and event_metrics.get("passed") and accepted_positions >= 10)
    selection="EMPIRICAL_PRIMARY_CANDIDATE" if overall_pass else "PERSISTENCE_FALLBACK_NETWORK_FAILED_ACCEPTANCE"
    payload={"schema_version":"1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"data_as_of":str(latest),
             "scope":"ALL_16_HX","method_status":"CANDIDATE","selected_operational_method":selection,
             "scheduler_replacement_allowed":False,"network_validation":metrics,
             "cleaning_event_validation":{"metrics":event_metrics,"events":event_rows},
             "model_coverage_gate":{"accepted_assets":accepted_positions,"required":10,"passed":accepted_positions>=10},
             "overall_acceptance_passed":overall_pass,"hx_models":model_rows,
             "latest_network":latest_network,"single_hx_counterfactuals":singles,"pairwise_interactions":interactions,
             "datasheet_diagnostics":datasheet,
             "warnings":["Datasheet track is design-only and has partial/OCR-limited coverage.","E101G remains inferred-only.","Scheduler remains on its existing reduced-form method until network acceptance passes."],}
    payload["plots"]=_plots(validation,model_rows,singles,datasheet,latest_network)
    (DASH/"hybrid_network_model.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    validation.reset_index().to_csv(DATA/"Hybrid_Network_CIT_Validation.csv",index=False)
    print(f"Wrote hybrid_network_model.json: {len(model_rows)} HX, validation={metrics}, plots={len(payload['plots'])}")


if __name__=="__main__": main()
