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
from src.events.cleaning_detection import detect_signal_recoveries


ANALYSIS_STATUS = "EXPLORATORY_SIGNAL_INFERRED"


def build_cycles(physics: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    accepted = events[events.event_status != "REJECTED_SIGNAL_EVENT"].copy()
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


def plot_hx(physics: pd.DataFrame, events: pd.DataFrame, hx_id: str, output: Path) -> None:
    hx = physics[physics.hx_id == hx_id].copy().sort_values("timestamp")
    if hx.empty:
        return
    valid = hx.operating_valid & hx.ua_valid
    colors = {
        "CLEANING_CANDIDATE": "tab:green",
        "BYPASS_OR_SWITCH_CANDIDATE": "tab:blue",
        "TAM_ASSOCIATED_RECOVERY": "tab:orange",
        "UNEXPLAINED_RECOVERY": "tab:purple",
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
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    physics = pd.read_csv(args.physics)
    physics["timestamp"] = pd.to_datetime(physics.timestamp, utc=True).dt.tz_convert("Asia/Bangkok")
    screening = config["screening"]

    event_frames = []
    summary_rows = []
    feasibility_rows = []
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
            tam_dates=config["major_shutdown_dates"], **screening,
        )
        if not detected.empty:
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
            "unexplained_recoveries": int((detected.event_status == "UNEXPLAINED_RECOVERY").sum()) if not detected.empty else 0,
            "tam_associated_recoveries": int((detected.event_status == "TAM_ASSOCIATED_RECOVERY").sum()) if not detected.empty else 0,
            "rejected_signal_events": int((detected.event_status == "REJECTED_SIGNAL_EVENT").sum()) if not detected.empty else 0,
            "analysis_status": ANALYSIS_STATUS, "cleaning_event_confirmed": False,
            "clean_condition_confirmed": False,
            "warning_code": "NO_MAINTENANCE_EVIDENCE",
        })

    event_columns = [
        "event_id", "hx_id", "event_timestamp", "event_status", "event_confidence",
        "feasibility_status", "cleaning_event_confirmed", "clean_condition_confirmed",
    ]
    events = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame(columns=event_columns)
    cycles = build_cycles(physics, events) if not events.empty else pd.DataFrame()
    table_dir = ROOT / "reports/tables/mvp_real_data/signal_inferred_cleaning"
    figure_dir = ROOT / "reports/figures/mvp_real_data/signal_inferred_cleaning"
    table_dir.mkdir(parents=True, exist_ok=True)
    events.to_csv(table_dir / "signal_recovery_candidates.csv", index=False)
    pd.DataFrame(summary_rows).to_csv(table_dir / "hx_signal_screening_summary.csv", index=False)
    pd.DataFrame(feasibility_rows).to_csv(table_dir / "bypass_cleaning_feasibility.csv", index=False)
    cycles.to_csv(table_dir / "exploratory_signal_cycles.csv", index=False)
    for hx_id in physics.hx_id.unique():
        plot_hx(physics, events, hx_id, figure_dir)
    print(pd.DataFrame(summary_rows).to_string(index=False))


if __name__ == "__main__":
    main()
