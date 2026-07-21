"""Create an engineering-review queue for candidate clean windows.

This stage never calculates clean UA, fouling indicators, or CIT impact.  It
keeps detected events immutable and treats every proposed window as CANDIDATE.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DEFAULT = Path(r"C:\Desktop\Bangchak Internship 2026\Data")


def load_event_evidence(data_dir: Path) -> pd.DataFrame:
    """Combine evidence without converting automated signals to confirmations."""
    parts = []
    primary = data_dir / "Cleaning_Events.csv"
    if primary.exists():
        frame = pd.read_csv(primary)
        for row in frame.itertuples(index=False):
            is_tam = str(row.event_status) == "CONFIRMED_TAM"
            parts.append({"hx_id": row.HX, "event_date": row.date,
                          "event_type_reported": row.type,
                          "evidence_source": primary.name,
                          "evidence_class": "CONFIRMED_TAM_CONTEXT" if is_tam else "DETECTED_EVENT_SIGNAL",
                          "source_confidence": row.confidence,
                          "review_status": "REVIEW_REQUIRED",
                          "notes": "TAM context only; does not prove this HX was cleaned." if is_tam else
                                   "Detected recovery/switch signal; maintenance confirmation absent."})
    validation = data_dir / "Cleaning_Event_Validation.csv"
    if validation.exists():
        frame = pd.read_csv(validation)
        for row in frame.itertuples(index=False):
            parts.append({"hx_id": row.HX, "event_date": row.event_date,
                          "event_type_reported": row.event_type,
                          "evidence_source": validation.name,
                          "evidence_class": "AUTOMATED_Q_CIT_SIGNAL",
                          "source_confidence": "MODEL_DERIVED",
                          "review_status": "REVIEW_REQUIRED",
                          "notes": "validated_as_cleaning is an automated field, not a maintenance approval."})
    deep = data_dir / "Cleaning_Event_Deepdive.csv"
    if deep.exists():
        frame = pd.read_csv(deep)
        for row in frame.itertuples(index=False):
            parts.append({"hx_id": row.HX, "event_date": row.Event_date,
                          "event_type_reported": row.Event_type,
                          "evidence_source": deep.name,
                          "evidence_class": "DETECTED_EVENT_SIGNAL",
                          "source_confidence": "UNCONFIRMED",
                          "review_status": "REVIEW_REQUIRED",
                          "notes": "Before/after diagnostic only; not a confirmed cleaning record."})
    evidence = pd.DataFrame(parts)
    if evidence.empty:
        return evidence
    evidence["event_date"] = pd.to_datetime(evidence.event_date, errors="coerce")
    return evidence.dropna(subset=["event_date"]).sort_values(["hx_id", "event_date"])


def propose_post_event_windows(physics: pd.DataFrame, evidence: pd.DataFrame,
                               *, min_records: int = 14, search_days: int = 45) -> pd.DataFrame:
    """Select eligible post-event observations for review, never approval."""
    rows = []
    if evidence.empty:
        return pd.DataFrame(rows)
    physics = physics.copy()
    physics["timestamp"] = pd.to_datetime(physics.timestamp, utc=True).dt.tz_convert("Asia/Bangkok")
    for (hx_id, event_date), group in evidence.groupby(["hx_id", "event_date"]):
        hx = physics[physics.hx_id == hx_id].sort_values("timestamp")
        if hx.empty:
            continue
        event_ts = pd.Timestamp(event_date).tz_localize("Asia/Bangkok")
        eligible = hx[(hx.timestamp > event_ts) &
                      (hx.timestamp <= event_ts + pd.Timedelta(days=search_days)) &
                      hx.operating_valid & hx.ua_valid & hx.ua_w_m2_k.notna()]
        selected = eligible.head(min_records)
        sources = ";".join(sorted(group.evidence_source.unique()))
        classes = ";".join(sorted(group.evidence_class.unique()))
        enough = len(selected) >= min_records
        rows.append({"hx_id": hx_id, "event_date": event_ts,
                     "event_evidence_class": classes, "evidence_sources": sources,
                     "candidate_start": selected.timestamp.min() if len(selected) else pd.NaT,
                     "candidate_end": selected.timestamp.max() if len(selected) else pd.NaT,
                     "valid_record_count": int(len(selected)),
                     "median_ua_w_m2_k": float(selected.ua_w_m2_k.median()) if len(selected) else None,
                     "ua_variability_cv": float(selected.ua_w_m2_k.std() / selected.ua_w_m2_k.mean()) if len(selected) > 1 else None,
                     "crude_flow_variability_cv": float(selected.cold_flow_m3_h.std() / selected.cold_flow_m3_h.mean()) if len(selected) > 1 else None,
                     "temperature_stability_mean_std_c": float(selected[["cold_in_c","cold_out_c","hot_in_c","hot_out_c"]].std().mean()) if len(selected) > 1 else None,
                     "evidence": "Eligible operating-valid post-event records; event still requires engineering review.",
                     "exclusions": "Startup, transient, invalid-sensor, missing-SG, and invalid-UA records excluded.",
                     "status": "CANDIDATE" if enough else "INSUFFICIENT_VALID_RECORDS",
                     "engineer_decision": "PENDING",
                     "engineer_notes": ""})
    return pd.DataFrame(rows).sort_values(["hx_id", "event_date"])


def plot_review_overlays(physics: pd.DataFrame, evidence: pd.DataFrame,
                         candidates: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    physics = physics.copy()
    physics["timestamp"] = pd.to_datetime(physics.timestamp, utc=True).dt.tz_convert("Asia/Bangkok")
    for hx_id, hx in physics.groupby("hx_id"):
        ev = evidence[evidence.hx_id == hx_id]
        can = candidates[candidates.hx_id == hx_id]
        if ev.empty or not hx.ua_w_m2_k.notna().any():
            continue
        fig, (ax, state_ax) = plt.subplots(2, 1, figsize=(16, 7), sharex=True,
                                           gridspec_kw={"height_ratios": [4, 1]})
        valid = hx.ua_valid & hx.ua_w_m2_k.notna()
        ax.plot(hx.timestamp, hx.ua_w_m2_k, color="#bdbdbd", lw=.6, label="U raw calculation")
        ax.scatter(hx.loc[valid, "timestamp"], hx.loc[valid, "ua_w_m2_k"], s=8,
                   color="#2166ac", label="Operating/calculation valid")
        for row in ev.itertuples(index=False):
            color = "black" if row.evidence_class == "CONFIRMED_TAM_CONTEXT" else "#e66101"
            ax.axvline(pd.Timestamp(row.event_date).tz_localize("Asia/Bangkok"), color=color,
                       ls="--", lw=.8, alpha=.65)
        for row in can.itertuples(index=False):
            if pd.notna(row.candidate_start) and row.status == "CANDIDATE":
                ax.axvspan(row.candidate_start, row.candidate_end, color="#5aae61", alpha=.15)
        ax.set_ylabel("U (W/m²·K)"); ax.set_title(f"{hx_id} — UA with event evidence and candidate review windows")
        ax.legend(fontsize=8, ncol=3); ax.grid(alpha=.2)
        state_codes = {"INVALID_SENSOR":0,"SHUTDOWN":1,"STARTUP":2,"TRANSIENT":3,"STEADY":4}
        state_ax.scatter(hx.timestamp, hx.operating_state.map(state_codes), s=7, c=hx.operating_state.map(state_codes), cmap="viridis")
        state_ax.set_yticks(list(state_codes.values())); state_ax.set_yticklabels(list(state_codes)); state_ax.set_ylabel("State"); state_ax.set_xlabel("Time (Asia/Bangkok)")
        fig.tight_layout(); fig.savefig(output_dir / f"{hx_id}_clean_window_review.png", dpi=140, bbox_inches="tight"); plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DATA_DEFAULT)
    parser.add_argument("--tables", type=Path, default=ROOT / "reports/tables/mvp_real_data")
    parser.add_argument("--figures", type=Path, default=ROOT / "reports/figures/mvp_real_data/clean_window_review")
    args = parser.parse_args()
    physics = pd.read_csv(args.tables / "hx_physics_validation.csv")
    evidence = load_event_evidence(args.data_dir)
    candidates = propose_post_event_windows(physics, evidence)
    out = args.tables / "clean_window_review"; out.mkdir(parents=True, exist_ok=True)
    evidence.to_csv(out / "event_evidence_register.csv", index=False)
    candidates.to_csv(out / "candidate_post_event_windows.csv", index=False)
    plot_review_overlays(physics, evidence, candidates, args.figures)
    print(f"Evidence records: {len(evidence)}")
    print(f"Candidate review rows: {len(candidates)}")
    print("No clean baseline, fouling indicator, or CIT impact was calculated.")


if __name__ == "__main__":
    main()
