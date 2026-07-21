"""Screen real-data UA recoveries against plant bypass feasibility.

Runtime outputs are exploratory and never populate canonical clean-baseline,
fouling-index, CIT, recommendation, forecast, or optimization artifacts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.domain.bypass import BYPASS_CONFIG, feasibility_label
from src.events.cleaning_detection import (
    detect_plant_tam_windows, detect_signal_recoveries, matched_condition_review,
    review_hx_tam_recovery,
)
from src.validation.real_data import load_dcs_matrix, load_pilot_config, resolve_tag


ANALYSIS_STATUS = "EXPLORATORY_SIGNAL_INFERRED"


def build_cycles(physics: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    accepted = events[events.event_status.isin([
        "CLEANING_CANDIDATE", "BYPASS_OR_SWITCH_CANDIDATE", "TAM_ASSOCIATED_RECOVERY"
    ])].copy()
    for hx_id, group in accepted.groupby("hx_id"):
        group = group.sort_values("event_timestamp")
        hx = physics[(physics.hx_id == hx_id) & physics.operating_valid & physics.ua_valid].copy()
        hx["timestamp"] = pd.to_datetime(hx.timestamp)
        for number, (left, right) in enumerate(zip(group.itertuples(), group.iloc[1:].itertuples()), 1):
            cycle = hx[(hx.timestamp >= left.event_timestamp) & (hx.timestamp < right.event_timestamp)]
            rows.append({
                "hx_id": hx_id, "cycle_number": number,
                "cycle_start": left.event_timestamp, "cycle_end": right.event_timestamp,
                "start_event_status": left.event_status, "end_event_status": right.event_status,
                "valid_records": len(cycle), "start_median_ua_kw_k": cycle.ua_value.head(7).median(),
                "end_median_ua_kw_k": cycle.ua_value.tail(7).median(),
                "ua_change_fraction": (
                    cycle.ua_value.tail(7).median() / cycle.ua_value.head(7).median() - 1
                    if len(cycle) >= 14 and cycle.ua_value.head(7).median() > 0 else None
                ),
                "cycle_status": "EXPLORATORY_SIGNAL_DEFINED",
                "cleaning_events_confirmed": False,
                "warning_code": "CYCLE_BOUNDARIES_ARE_SIGNAL_CANDIDATES",
            })
    return pd.DataFrame(rows)


def annual_frequency_check(events: pd.DataFrame, config: dict, data_end) -> pd.DataFrame:
    guidance = config["engineering_guidance"]
    priority = set(guidance["high_review_priority_hx"])
    eligible = events[
        events.hx_id.isin(priority)
        & (events.event_status != "TAM_ASSOCIATED_RECOVERY")
        & (
            events.event_status.isin(["CLEANING_CANDIDATE", "BYPASS_OR_SWITCH_CANDIDATE"])
            | (events.matched_review_status == "MATCHED_RECOVERY_PLAUSIBLE")
        )
    ].copy()
    eligible["year"] = pd.to_datetime(eligible.event_timestamp).dt.year
    start_year = int(pd.to_datetime(events.event_timestamp).dt.year.min()) if not events.empty else pd.Timestamp(data_end).year
    end_year = pd.Timestamp(data_end).year
    rows = []
    for year in range(start_year, end_year + 1):
        count = int((eligible.year == year).sum())
        complete_year = year < end_year or (pd.Timestamp(data_end).month == 12 and pd.Timestamp(data_end).day == 31)
        if not complete_year:
            status = "PARTIAL_YEAR_NOT_ASSESSED"
        elif count < guidance["expected_cleaning_actions_per_year_min"]:
            status = "POSSIBLE_UNDER_DETECTION"
        elif count > guidance["expected_cleaning_actions_per_year_max"]:
            status = "POSSIBLE_OVER_DETECTION"
        else:
            status = "CONSISTENT_WITH_ENGINEERING_EXPECTATION"
        rows.append({
            "year": year, "detected_priority_hx_events": count,
            "expected_min_actions": guidance["expected_cleaning_actions_per_year_min"],
            "expected_max_actions": guidance["expected_cleaning_actions_per_year_max"],
            "frequency_scope": guidance["frequency_scope"], "frequency_consistency_status": status,
            "expectation_creates_events": False, "cleaning_events_confirmed": False,
        })
    return pd.DataFrame(rows)


def plot_hx(physics: pd.DataFrame, events: pd.DataFrame, hx_id: str, output: Path) -> None:
    hx = physics[physics.hx_id == hx_id].copy().sort_values("timestamp")
    if hx.empty:
        return
    valid = hx.operating_valid & hx.ua_valid
    colors = {
        "CLEANING_CANDIDATE": "tab:green",
        "BYPASS_OR_SWITCH_CANDIDATE": "tab:blue",
        "TAM_ASSOCIATED_RECOVERY": "tab:orange",
        "NOT_CLEANING_ELIGIBLE_MID_RUN": "tab:purple",
        "REJECTED_SIGNAL_EVENT": "tab:red",
    }
    fig, axes = plt.subplots(3, 1, figsize=(16, 10), sharex=True)
    axes[0].plot(hx.loc[valid, "timestamp"], hx.loc[valid, "ua_value"], lw=0.8, label="Valid UA")
    axes[1].plot(hx.timestamp, hx.cold_flow_m3_h, lw=0.7)
    axes[2].plot(hx.timestamp, hx.lmtd_value, lw=0.7)
    for event in events[events.hx_id == hx_id].itertuples():
        for axis in axes:
            axis.axvline(event.event_timestamp, color=colors[event.event_status], alpha=0.45, lw=1)
    axes[0].set_ylabel("UA (kW/K)")
    axes[1].set_ylabel("Crude flow (m³/h)")
    axes[2].set_ylabel("LMTD (°C)")
    axes[2].set_xlabel("Time (Asia/Bangkok)")
    for axis in axes:
        axis.grid(alpha=0.2)
    axes[0].set_title(f"{hx_id} — signal-inferred recovery screening (NOT CONFIRMED CLEANING)")
    output.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output / f"{hx_id}_signal_recovery_review.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config/signal_inferred_cleaning.json")
    parser.add_argument("--physics", type=Path, default=ROOT / "reports/tables/mvp_real_data/hx_physics_validation.csv")
    parser.add_argument("--pilot-config", type=Path, default=ROOT / "config/mvp_real_data_pilot.json")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    physics = pd.read_csv(args.physics)
    physics["timestamp"] = pd.to_datetime(physics.timestamp, utc=True).dt.tz_convert("Asia/Bangkok")
    pilot_config = load_pilot_config(args.pilot_config)
    raw, _ = load_dcs_matrix(pilot_config)
    tam_config = config["tam_detection"]
    total_charge_tag = resolve_tag(raw.columns, tam_config["total_charge_tag"], pilot_config.get("aliases", {}))
    if total_charge_tag is None:
        raise ValueError(f"TAM total-charge tag is unavailable: {tam_config['total_charge_tag']}")
    plant_tam = detect_plant_tam_windows(
        raw.timestamp, raw[total_charge_tag],
        flow_threshold_m3_h=tam_config["flow_threshold_m3_h"],
        minimum_consecutive_records=tam_config["minimum_consecutive_records"],
        source_status=tam_config["source_status"],
    )
    expected = {row["tam_id"]: row for row in tam_config.get("expected_windows_for_review", [])}
    if not plant_tam.empty:
        plant_tam["source_tag"] = total_charge_tag
        plant_tam["source_unit"] = tam_config["total_charge_unit"]
        plant_tam["expected_window_start"] = plant_tam.tam_id.map(lambda value: expected.get(value, {}).get("start"))
        plant_tam["expected_window_end"] = plant_tam.tam_id.map(lambda value: expected.get(value, {}).get("end"))
        plant_tam["expected_window_match"] = plant_tam.apply(
            lambda row: (
                str(row.tam_start.date()) == row.expected_window_start
                and str(row.tam_end.date()) == row.expected_window_end
            ), axis=1,
        )
    tam_restart_dates = [str(value) for value in plant_tam.restart_from.dropna()]
    screening = config["screening"]
    priority_hx = set(config["engineering_guidance"]["high_review_priority_hx"])

    event_frames = []
    summary_rows = []
    feasibility_rows = []
    tam_review_rows = []
    for hx_id, group in physics.groupby("hx_id"):
        feasibility = feasibility_label(hx_id)
        bypass = BYPASS_CONFIG.get(hx_id, {})
        feasibility_rows.append({
            "hx_id": hx_id, "feasibility_status": feasibility,
            "online_mode": bypass.get("online_mode", "unavailable"),
            "duty_fraction": bypass.get("duty_fraction"),
            "bypass_source": bypass.get("source", "UNAVAILABLE"),
            "feasibility_is_cleaning_evidence": False,
        })
        detected = detect_signal_recoveries(
            group, hx_id=hx_id, feasibility=feasibility,
            tam_dates=tam_restart_dates, **screening,
        )
        for tam_event in plant_tam.to_dict("records"):
            tam_review_rows.append(review_hx_tam_recovery(
                group, tam_event,
                comparison_window_days=tam_config["comparison_window_days"],
                minimum_valid_records=tam_config["minimum_valid_records"],
                recovery_threshold_fraction=tam_config["recovery_threshold_fraction"],
                persistence_days=tam_config["persistence_days"],
                flow_change_max_fraction=screening["flow_change_max_fraction"],
                lmtd_change_max_fraction=screening["lmtd_change_max_fraction"],
                hot_in_change_max_c=screening["hot_in_change_max_c"],
                matched_review_config=config["matched_condition_review"],
            ))
        if not detected.empty:
            detected["engineering_review_priority"] = "HIGH" if hx_id in priority_hx else "STANDARD"
            if hx_id in priority_hx:
                matched = [matched_condition_review(
                    group, event.event_timestamp, **config["matched_condition_review"]
                ) for event in detected.itertuples()]
                detected = pd.concat([detected.reset_index(drop=True), pd.DataFrame(matched)], axis=1)
            else:
                detected["matched_review_status"] = "NOT_PRIORITY_SCREENED"
                detected["matched_pair_count"] = None
                detected["matched_median_recovery_fraction"] = None
                detected["matched_recovery_iqr"] = None
                detected["matched_condition_cleaning_confirmed"] = False
            detected["analysis_status"] = ANALYSIS_STATUS
            detected["interpretation"] = config["interpretation"]
            event_frames.append(detected)
        summary_rows.append({
            "hx_id": hx_id, "feasibility_status": feasibility,
            "screened_valid_records": int((group.operating_valid & group.ua_valid).sum()),
            "non_rejected_recovery_signals": int((detected.event_status != "REJECTED_SIGNAL_EVENT").sum()) if not detected.empty else 0,
            "feasible_cleaning_or_switch_candidates": int(detected.event_status.isin([
                "CLEANING_CANDIDATE", "BYPASS_OR_SWITCH_CANDIDATE"
            ]).sum()) if not detected.empty else 0,
            "tam_only_midrun_ineligible_signals": int((detected.event_status == "NOT_CLEANING_ELIGIBLE_MID_RUN").sum()) if not detected.empty else 0,
            "tam_associated_recoveries": int((detected.event_status == "TAM_ASSOCIATED_RECOVERY").sum()) if not detected.empty else 0,
            "rejected_signal_events": int((detected.event_status == "REJECTED_SIGNAL_EVENT").sum()) if not detected.empty else 0,
            "analysis_status": ANALYSIS_STATUS, "cleaning_event_confirmed": False,
            "clean_condition_confirmed": False,
            "warning_code": "NO_MAINTENANCE_EVIDENCE",
        })

    analyzed_hx = set(physics.hx_id.unique())
    for hx_id, hx_config in pilot_config["heat_exchangers"].items():
        if hx_id in analyzed_hx:
            continue
        reason = hx_config.get("unavailable_reason", hx_config.get("blocked_reason", "NO_PHYSICS_RECORDS"))
        summary_rows.append({
            "hx_id": hx_id, "feasibility_status": feasibility_label(hx_id),
            "screened_valid_records": 0, "non_rejected_recovery_signals": 0,
            "feasible_cleaning_or_switch_candidates": 0,
            "tam_only_midrun_ineligible_signals": 0, "tam_associated_recoveries": 0,
            "rejected_signal_events": 0, "analysis_status": "UNAVAILABLE_OR_BLOCKED",
            "cleaning_event_confirmed": False, "clean_condition_confirmed": False,
            "warning_code": reason,
        })
        for tam_event in plant_tam.to_dict("records"):
            tam_review_rows.append({
                "tam_id": tam_event["tam_id"], "hx_id": hx_id,
                "tam_start": tam_event["tam_start"], "tam_end": tam_event["tam_end"],
                "restart_from": tam_event["restart_from"],
                "pre_valid_records": 0, "post_valid_records": 0,
                "tam_recovery_status": "TAM_ASSOCIATED_INSUFFICIENT_DATA",
                "plant_tam_status": tam_event["plant_tam_status"],
                "hx_exposed_to_tam": True, "hx_performance_recovery_observed": False,
                "individual_hx_cleaning_confirmed": False, "clean_condition_confirmed": False,
                "warning_code": reason,
                "interpretation": "HX performance is unavailable or blocked; individual cleaning is not confirmed.",
            })

    event_columns = [
        "event_id", "hx_id", "event_timestamp", "event_status", "event_confidence",
        "feasibility_status", "cleaning_event_confirmed", "clean_condition_confirmed",
    ]
    events = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame(columns=event_columns)
    cycles = build_cycles(physics, events) if not events.empty else pd.DataFrame()
    frequency = annual_frequency_check(events, config, physics.timestamp.max())
    review_queue = events[events.hx_id.isin(priority_hx)].copy()
    review_queue["review_queue_rank"] = review_queue.apply(
        lambda row: 1 if row.get("matched_review_status") == "MATCHED_RECOVERY_PLAUSIBLE"
        else 2 if row.event_status in {"CLEANING_CANDIDATE", "BYPASS_OR_SWITCH_CANDIDATE"}
        else 3 if row.get("matched_review_status") == "INSUFFICIENT_MATCHED_DATA" else 4,
        axis=1,
    )
    review_queue = review_queue.sort_values(["review_queue_rank", "hx_id", "event_timestamp"])
    table_dir = ROOT / "reports/tables/mvp_real_data/signal_inferred_cleaning"
    figure_dir = ROOT / "reports/figures/mvp_real_data/signal_inferred_cleaning"
    table_dir.mkdir(parents=True, exist_ok=True)
    events.to_csv(table_dir / "signal_recovery_candidates.csv", index=False)
    plant_tam.to_csv(table_dir / "plant_tam_events.csv", index=False)
    pd.DataFrame(tam_review_rows).to_csv(table_dir / "hx_tam_event_study.csv", index=False)
    pd.DataFrame(summary_rows).to_csv(table_dir / "hx_signal_screening_summary.csv", index=False)
    pd.DataFrame(feasibility_rows).to_csv(table_dir / "bypass_cleaning_feasibility.csv", index=False)
    cycles.to_csv(table_dir / "exploratory_signal_cycles.csv", index=False)
    review_queue.to_csv(table_dir / "priority_hx_event_review_queue.csv", index=False)
    frequency.to_csv(table_dir / "annual_frequency_sanity_check.csv", index=False)
    for hx_id in physics.hx_id.unique():
        plot_hx(physics, events, hx_id, figure_dir)
    print(pd.DataFrame(summary_rows).to_string(index=False))


if __name__ == "__main__":
    main()
