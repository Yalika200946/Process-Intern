"""Build runtime-only CPHT flow-balance and configuration-state evidence."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.domain.configuration_states import (
    add_transition_buffer, classify_e101_state, expected_residue_lineup,
    flow_balance, reclassify_signal_event,
)
from src.validation.real_data import load_dcs_matrix, load_pilot_config, resolve_tag

BASE = ROOT / "reports/tables/mvp_real_data/configuration_states"
FIG = ROOT / "reports/figures/mvp_real_data/configuration_states"


def _numeric(raw: pd.DataFrame, tag: str, aliases: dict) -> pd.Series:
    resolved = resolve_tag(raw.columns, tag, aliases)
    return pd.to_numeric(raw[resolved], errors="coerce") if resolved else pd.Series(np.nan, index=raw.index)


def build_flow_and_e101_state(raw: pd.DataFrame, config: dict, topology: dict):
    rules = topology["inference_rules"]; aliases = config.get("aliases", {})
    total = _numeric(raw, rules["total_crude_tag"], aliases)
    cpht1_parts = [_numeric(raw, tag, aliases) for tag in rules["cpht1_branch_flow_tags"]]
    cpht2_parts = [_numeric(raw, tag, aliases) for tag in rules["cpht2_branch_flow_tags"]]
    rows1, rows2, states = [], [], []
    for i, timestamp in enumerate(raw.timestamp):
        b1 = flow_balance(total.iloc[i], [part.iloc[i] for part in cpht1_parts],
                          tolerance_fraction=rules["flow_balance_relative_tolerance"])
        rows1.append({"timestamp": timestamp, "total_crude_m3_h": total.iloc[i], **b1,
                      "residual_interpretation": "UNMEASURED_E101G_OR_BOUNDARY_MISMATCH",
                      "e101g_flow_confirmed": False})
        b2 = flow_balance(total.iloc[i], [part.iloc[i] for part in cpht2_parts],
                          tolerance_fraction=rules["flow_balance_relative_tolerance"])
        rows2.append({"timestamp": timestamp, "total_crude_m3_h": total.iloc[i], **b2})
        states.append({"timestamp": timestamp, **classify_e101_state(
            total.iloc[i], cpht1_parts[2].iloc[i],
            total_min=rules["operating_total_flow_min_m3_h"],
            branch_min=rules["branch_operating_flow_min_m3_h"],
        ), "e101g_operation_confirmed": False})
    state = add_transition_buffer(pd.DataFrame(states), rules["transition_buffer_records"])
    return pd.DataFrame(rows1), pd.DataFrame(rows2), state


def build_state_aware_performance(physics: pd.DataFrame, e101: pd.DataFrame,
                                  events: pd.DataFrame | None = None,
                                  event_window_days: int = 3) -> pd.DataFrame:
    result = physics.copy(); result["timestamp"] = pd.to_datetime(result.timestamp, utc=True).dt.tz_convert("Asia/Bangkok")
    e = e101.copy(); e["timestamp"] = pd.to_datetime(e.timestamp, utc=True).dt.tz_convert("Asia/Bangkok")
    lookup = e.set_index("timestamp")[["configuration_state", "configuration_confidence",
                                       "eligible_for_fouling_fit"]]
    result["configuration_state"] = "STATIC_MEMBERSHIP_ONLY"
    result["configuration_confidence"] = "MEDIUM"
    result["configuration_evidence_status"] = "ENGINEER_CONFIRMED_DCS_EVIDENCE"
    result["eligible_for_state_aware_fouling_fit"] = result.operating_valid & result.ua_valid
    ef = result.hx_id.eq("E101EF")
    joined = result.loc[ef, ["timestamp"]].join(lookup, on="timestamp")
    result.loc[ef, "configuration_state"] = joined.configuration_state.to_numpy()
    result.loc[ef, "configuration_confidence"] = joined.configuration_confidence.to_numpy()
    result.loc[ef, "eligible_for_state_aware_fouling_fit"] = (
        result.loc[ef, "operating_valid"].to_numpy() & result.loc[ef, "ua_valid"].to_numpy()
        & joined.eligible_for_fouling_fit.fillna(False).to_numpy()
    )
    residue_hx = {"E113A", "E112C", "E112AB", "E108AB"}
    residue = result.hx_id.isin(residue_hx)
    result.loc[residue, "configuration_state"] = "RESIDUE_BASE_LINEUP_NO_VALVE_CONFIRMATION"
    result.loc[residue, "configuration_confidence"] = "LOW"
    # Absence of a signal is not confirmation of the normal valve lineup. Retain
    # otherwise-valid records provisionally, but mask windows around candidate
    # configuration changes so they cannot enter a state-aware fouling fit.
    residue_event = pd.Series(False, index=result.index)
    if events is not None and not events.empty:
        candidate = events[
            events.hx_id.isin(residue_hx)
            & ~events.event_status.isin(["REJECTED_SIGNAL_EVENT", "NOT_CLEANING_ELIGIBLE_MID_RUN"])
        ].copy()
        candidate["event_timestamp"] = pd.to_datetime(candidate.event_timestamp, utc=True).dt.tz_convert("Asia/Bangkok")
        for event in candidate.itertuples():
            distance = (result.timestamp - event.event_timestamp).abs()
            residue_event |= residue & distance.le(pd.Timedelta(days=event_window_days))
    result.loc[residue_event, "configuration_state"] = "RESIDUE_EVENT_CONFIGURATION_CANDIDATE"
    result.loc[residue_event, "configuration_confidence"] = "LOW"
    result.loc[residue_event, "eligible_for_state_aware_fouling_fit"] = False
    result["state_aware_exclusion_reason"] = np.where(
        result.eligible_for_state_aware_fouling_fit, "",
        np.where(residue_event, "SIGNAL_EVENT_WINDOW_WITHOUT_VALVE_CONFIRMATION",
                 np.where(residue, "ORIGINAL_OPERATING_OR_UA_INVALID",
                 np.where(ef, "E101_SUBSTITUTION_OR_TRANSITION", "ORIGINAL_OPERATING_OR_UA_INVALID")))
    )
    return result


def reclassify_events(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if events.empty:
        return events.copy(), pd.DataFrame()
    reviewed, lineups = [], []
    for row in events.to_dict("records"):
        reviewed.append({**row, **reclassify_signal_event(row["hx_id"], row["event_status"]),
                         "cleaning_event_confirmed": False})
        lineup = expected_residue_lineup(row["hx_id"])
        if lineup["substitution_evidence_required"]:
            lineups.append({"event_id": row.get("event_id"), "event_timestamp": row["event_timestamp"],
                            "cleaning_hx": row["hx_id"], **lineup,
                            "actual_lineup_status": "UNKNOWN_NO_VALVE_HISTORY"})
    return pd.DataFrame(reviewed), pd.DataFrame(lineups)


def _plot_balance(frame: pd.DataFrame, title: str, output: Path):
    fig, axes = plt.subplots(2, 1, figsize=(15, 7), sharex=True)
    axes[0].plot(frame.timestamp, frame.total_crude_m3_h, label="Total crude (measured)", lw=.8)
    axes[0].plot(frame.timestamp, frame.component_sum_m3_h, label="Branch sum (measured)", lw=.8)
    axes[0].set_ylabel("Crude flow (m3/h)"); axes[0].legend(); axes[0].grid(alpha=.2)
    axes[1].plot(frame.timestamp, frame.residual_m3_h, lw=.8)
    axes[1].axhline(0, color="black", lw=.7); axes[1].set_ylabel("Residual (m3/h)")
    axes[1].set_xlabel("Time (Asia/Bangkok)"); axes[1].grid(alpha=.2)
    fig.suptitle(title); fig.tight_layout(); fig.savefig(output, dpi=140, bbox_inches="tight"); plt.close(fig)


def main():
    pilot = load_pilot_config(ROOT / "config/mvp_real_data_pilot.json")
    topology = json.loads((ROOT / "config/configuration_topology.json").read_text(encoding="utf-8"))
    raw, _ = load_dcs_matrix(pilot)
    physics = pd.read_csv(ROOT / "reports/tables/mvp_real_data/hx_physics_validation.csv")
    events_path = ROOT / "reports/tables/mvp_real_data/signal_inferred_cleaning/signal_recovery_candidates.csv"
    events = pd.read_csv(events_path) if events_path.exists() else pd.DataFrame()
    cpht1, cpht2, e101 = build_flow_and_e101_state(raw, pilot, topology)
    performance = build_state_aware_performance(physics, e101, events)
    reviewed, lineups = reclassify_events(events)
    BASE.mkdir(parents=True, exist_ok=True); FIG.mkdir(parents=True, exist_ok=True)
    cpht1.to_csv(BASE / "cpht1_flow_balance.csv", index=False)
    cpht2.to_csv(BASE / "cpht2_flow_balance.csv", index=False)
    e101.to_csv(BASE / "e101_configuration_timeline.csv", index=False)
    performance.to_csv(BASE / "state_aware_hx_performance.csv", index=False)
    reviewed.to_csv(BASE / "state_aware_cleaning_candidates.csv", index=False)
    lineups.to_csv(BASE / "residue_expected_lineup_by_event.csv", index=False)
    pd.DataFrame([{
        "evidence_status": topology["evidence_status"],
        "cpht1_balance_within_tolerance_pct": 100 * cpht1.balance_status.eq("WITHIN_TOLERANCE").mean(),
        "cpht2_balance_within_tolerance_pct": 100 * cpht2.balance_status.eq("WITHIN_TOLERANCE").mean(),
        "e101g_substitution_candidate_records": int(e101.configuration_state.eq("E101G_SUBSTITUTED_INFERRED").sum()),
        "residue_actual_lineup_status": "SIGNAL_INFERRED_EVENT_WINDOWS_NO_VALVE_HISTORY",
        "confirmed_cleaning_events": 0,
        "network_cit_status": "BLOCKED_PENDING_STATE_AND_MIX_VALIDATION",
    }]).to_csv(BASE / "configuration_validation_summary.csv", index=False)
    _plot_balance(cpht1, "CPHT-1 measured flow balance (residual is not confirmed E101G flow)", FIG / "cpht1_flow_balance.png")
    _plot_balance(cpht2, "CPHT-2 measured branch-flow balance", FIG / "cpht2_flow_balance.png")
    print((BASE / "configuration_validation_summary.csv").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
