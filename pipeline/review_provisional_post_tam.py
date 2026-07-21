"""Engineering review of provisional post-TAM reference windows only.

No result from this module is an approved clean baseline.  Following-period
data are used only as review diagnostics and never enter a provisional median.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _eligible(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame.operating_valid & frame.ua_valid & frame.ua_w_m2_k.notna()].copy()


def _cv(series: pd.Series) -> float | None:
    mean = series.mean()
    return None if not np.isfinite(mean) or mean == 0 else float(series.std() / abs(mean))


def _median(series: pd.Series) -> float | None:
    value = series.median()
    return None if not np.isfinite(value) else float(value)


def assess_window(physics: pd.DataFrame, spec: dict, settings: dict) -> tuple[dict, pd.DataFrame]:
    """Return a provisional review row plus inward-only sensitivity records."""
    hx_id = spec["hx_id"]
    hx = physics[physics.hx_id == hx_id].sort_values("timestamp")
    start = pd.Timestamp(spec["start"], tz="Asia/Bangkok")
    end = pd.Timestamp(spec["end"], tz="Asia/Bangkok")
    raw_window = hx[(hx.timestamp >= start) & (hx.timestamp <= end)]
    window = _eligible(raw_window)
    pre = _eligible(hx[(hx.timestamp >= start - pd.Timedelta(days=settings["pre_review_days"])) &
                       (hx.timestamp < start)])
    post = _eligible(hx[(hx.timestamp > end) &
                        (hx.timestamp <= end + pd.Timedelta(days=settings["post_review_days"]))])
    median = _median(window.ua_w_m2_k)
    q1, q3 = window.ua_w_m2_k.quantile([.25, .75]) if len(window) else (np.nan, np.nan)
    pre_median, post_median = _median(pre.ua_w_m2_k), _median(post.ua_w_m2_k)
    recovery = None if median is None or pre_median in (None, 0) else (median - pre_median) / abs(pre_median)
    sustained = median is not None and post_median is not None and post_median >= 0.90 * median

    sensitivity = []
    for shift_start in settings["sensitivity_inward_shift_days"]:
        for shift_end in settings["sensitivity_inward_shift_days"]:
            s, e = start + pd.Timedelta(days=shift_start), end - pd.Timedelta(days=shift_end)
            subset = _eligible(hx[(hx.timestamp >= s) & (hx.timestamp <= e)])
            if e >= s and len(subset) >= 5:
                sensitivity.append({"hx_id": hx_id, "shift_start_days": shift_start,
                                    "shift_end_days": shift_end, "review_start": s,
                                    "review_end": e, "valid_record_count": len(subset),
                                    "provisional_median_ua_w_m2_k": _median(subset.ua_w_m2_k),
                                    "status": "PROVISIONAL_SENSITIVITY_ONLY"})
    sensitivity_df = pd.DataFrame(sensitivity)
    sens_values = sensitivity_df.provisional_median_ua_w_m2_k.dropna() if len(sensitivity_df) else pd.Series(dtype=float)
    sensitivity_span = None if median in (None, 0) or sens_values.empty else float((sens_values.max() - sens_values.min()) / abs(median))

    coverage = len(window) / len(raw_window) if len(raw_window) else 0
    flow_shift = None if pre.empty or window.empty or pre.cold_flow_m3_h.median() == 0 else float(
        (window.cold_flow_m3_h.median() - pre.cold_flow_m3_h.median()) / abs(pre.cold_flow_m3_h.median()))
    lmtd_shift = None if pre.empty or window.empty or pre.lmtd_value.median() == 0 else float(
        (window.lmtd_value.median() - pre.lmtd_value.median()) / abs(pre.lmtd_value.median()))
    inlet_shift = None if pre.empty or window.empty else float(window.cold_in_c.median() - pre.cold_in_c.median())
    sg_shift = None if pre.empty or window.empty else float(window.sg_15_6c.median() - pre.sg_15_6c.median())
    confounders = []
    if flow_shift is not None and abs(flow_shift) > .10: confounders.append(f"crude flow median changed {flow_shift:+.1%}")
    if lmtd_shift is not None and abs(lmtd_shift) > .10: confounders.append(f"LMTD median changed {lmtd_shift:+.1%}")
    if inlet_shift is not None and abs(inlet_shift) > 5: confounders.append(f"cold inlet median changed {inlet_shift:+.1f} degC")
    if sg_shift is not None and abs(sg_shift) > .01: confounders.append(f"SG median changed {sg_shift:+.4f}")

    evidence_for = []
    evidence_against = ["TAM does not prove individual HX cleaning."]
    ua_cv = _cv(window.ua_w_m2_k)
    if len(window) >= 14: evidence_for.append(f"{len(window)} valid steady-state records available.")
    if ua_cv is not None and ua_cv <= .10: evidence_for.append(f"UA is stable (CV={ua_cv:.1%}).")
    if recovery is not None and recovery > .10: evidence_for.append(f"UA is {recovery:.1%} above preceding-period median.")
    else: evidence_against.append("No clear >10% UA increase over the preceding-period median.")
    if sustained: evidence_for.append("Following-period median remains within 10% of the provisional median.")
    else: evidence_against.append("UA recovery is not sustained into the following review period.")
    if confounders: evidence_against.append("Observed change has operating-condition confounders: " + "; ".join(confounders))
    if sensitivity_span is not None and sensitivity_span > .10: evidence_against.append(f"Median is boundary-sensitive ({sensitivity_span:.1%} span).")

    if len(window) < 10:
        recommendation, confidence = "INSUFFICIENT_EVIDENCE", "LOW"
    elif coverage < .70 or (ua_cv is not None and ua_cv > .15):
        recommendation, confidence = "REVISE_WINDOW", "LOW"
    elif recovery is not None and recovery > .10 and sustained and not confounders and (sensitivity_span or 0) <= .10:
        recommendation, confidence = "APPROVE_WITH_LIMITATIONS", "MEDIUM"
    elif recovery is not None and recovery < -.10:
        recommendation, confidence = "REJECT_AS_CLEAN_REFERENCE", "MEDIUM"
    else:
        recommendation, confidence = "INSUFFICIENT_EVIDENCE", "LOW"

    sensor_status = "GOOD" if coverage >= .90 else "PARTIAL" if coverage >= .70 else "POOR"
    explanation = "No material flow/LMTD/inlet-temperature/SG shift detected." if not confounders else "; ".join(confounders)
    row = {"reference_status": "PROVISIONAL_POST_TAM_REFERENCE", "approval_status": "NOT_YET_APPROVED",
           "hx_id": hx_id, "proposed_start": start, "proposed_end": end,
           "valid_record_count": int(len(window)), "window_record_count": int(len(raw_window)),
           "median_ua": median, "median_ua_unit": "W/m2-K",
           "ua_iqr": None if not len(window) else float(q3 - q1),
           "ua_coefficient_of_variation": ua_cv,
           "crude_flow_variability": _cv(window.cold_flow_m3_h),
           "lmtd_variability": _cv(window.lmtd_value),
           "cold_in_temperature_variability": _cv(window.cold_in_c),
           "configuration_consistent": "PARTIALLY_VERIFIED_STATIC_MAPPING_NO_VALVE_STATUS",
           "sensor_quality_status": sensor_status,
           "pre_window_median_ua": pre_median, "post_window_median_ua": post_median,
           "apparent_ua_recovery": recovery, "sustained_recovery_diagnostic": bool(sustained),
           "median_sensitivity_relative_span": sensitivity_span,
           "operating_condition_explanation": explanation,
           "evidence_for_clean_state": " ".join(evidence_for) or "None established.",
           "evidence_against_clean_state": " ".join(evidence_against),
           "recommendation": recommendation, "confidence": confidence}
    return row, sensitivity_df


def plot_review(physics: pd.DataFrame, rows: pd.DataFrame, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for row in rows.itertuples(index=False):
        hx = physics[physics.hx_id == row.hx_id].sort_values("timestamp")
        start, end = row.proposed_start, row.proposed_end
        view = hx[(hx.timestamp >= start - pd.Timedelta(days=30)) &
                  (hx.timestamp <= end + pd.Timedelta(days=30))]
        fig, axes = plt.subplots(3, 1, figsize=(15, 10), sharex=True)
        axes[0].plot(view.timestamp, view.ua_w_m2_k, color="#999999", lw=.8)
        valid = view.operating_valid & view.ua_valid
        axes[0].scatter(view.loc[valid,"timestamp"],view.loc[valid,"ua_w_m2_k"],s=12,color="#2166ac",label="Valid steady-state U")
        axes[0].axvspan(start,end,color="#4daf4a",alpha=.18,label="PROVISIONAL window")
        axes[0].set_ylabel("U (W/m²·K)");axes[0].legend(fontsize=8);axes[0].set_title(f"{row.hx_id} — provisional post-TAM engineering review (NOT APPROVED)")
        axes[1].plot(view.timestamp,view.cold_flow_m3_h,label="Crude flow",color="#1b9e77");axes[1].set_ylabel("Flow (m³/h)");axes[1].legend(fontsize=8)
        axes[2].plot(view.timestamp,view.lmtd_value,label="LMTD",color="#d95f02");axes[2].plot(view.timestamp,view.cold_in_c,label="Cold inlet",color="#7570b3");axes[2].set_ylabel("Temperature difference / temperature (°C)");axes[2].set_xlabel("Time (Asia/Bangkok)");axes[2].legend(fontsize=8,ncol=2)
        for ax in axes: ax.axvspan(start,end,color="#4daf4a",alpha=.12);ax.grid(alpha=.2)
        fig.tight_layout();fig.savefig(output/f"{row.hx_id}_provisional_post_tam_review.png",dpi=140,bbox_inches="tight");plt.close(fig)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--config",type=Path,default=ROOT/"config/provisional_post_tam_windows.json");parser.add_argument("--physics",type=Path,default=ROOT/"reports/tables/mvp_real_data/hx_physics_validation.csv");args=parser.parse_args()
    settings=json.loads(args.config.read_text(encoding="utf-8"));physics=pd.read_csv(args.physics);physics["timestamp"]=pd.to_datetime(physics.timestamp,utc=True).dt.tz_convert("Asia/Bangkok")
    rows=[];sensitivity=[]
    for spec in settings["windows"]:
        row,sens=assess_window(physics,spec,settings);rows.append(row);sensitivity.append(sens)
    review=pd.DataFrame(rows);sens=pd.concat(sensitivity,ignore_index=True)
    out=ROOT/"reports/tables/mvp_real_data/provisional_post_tam_review";out.mkdir(parents=True,exist_ok=True)
    review.to_csv(out/"engineering_review.csv",index=False);sens.to_csv(out/"median_sensitivity.csv",index=False)
    plot_review(physics,review,ROOT/"reports/figures/mvp_real_data/provisional_post_tam_review")
    print(review[["hx_id","valid_record_count","median_ua","recommendation","confidence"]].to_string(index=False))
    print("All medians are PROVISIONAL and NOT YET APPROVED.")


if __name__=="__main__": main()
