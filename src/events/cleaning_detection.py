"""Signal-inferred cleaning candidates without claiming maintenance confirmation."""

from __future__ import annotations

import numpy as np
import pandas as pd


def score_cleaning_event(*, tam_record=False, maintenance_record=False, stable_recovery=False,
                         configuration_change=False, process_change=False):
    score = 0
    score += 5 if tam_record else 0
    score += 5 if maintenance_record else 0
    score += 2 if stable_recovery else 0
    score += 1 if configuration_change else 0
    score -= 3 if process_change else 0
    status = "CONFIRMED_TAM" if tam_record else "SWITCH_CANDIDATE" if configuration_change else "UNEXPLAINED_RECOVERY"
    return {
        "score": score, "event_status": status,
        "confirmed_clean": bool(maintenance_record and stable_recovery),
        "approval_status": "CANDIDATE",
        "warning": None if maintenance_record else "No authoritative maintenance record; event is not confirmed clean.",
    }


def detect_signal_recoveries(
    records: pd.DataFrame,
    *,
    hx_id: str,
    feasibility: str,
    tam_dates: list[str] | None = None,
    pre_records: int = 14,
    post_records: int = 14,
    minimum_records: int = 7,
    minimum_recovery_fraction: float = 0.05,
    high_confidence_recovery_fraction: float = 0.10,
    post_ua_cv_max: float = 0.15,
    flow_change_max_fraction: float = 0.10,
    lmtd_change_max_fraction: float = 0.10,
    hot_in_change_max_c: float = 5.0,
    cluster_days: int = 14,
) -> pd.DataFrame:
    """Screen sustained UA step recoveries using valid records only.

    The result is retrospective evidence screening. It never emits a confirmed
    cleaning event or a confirmed clean state. Operating changes are retained as
    rejected candidates so the reason for exclusion remains auditable.
    """
    required = {
        "timestamp", "ua_value", "operating_valid", "ua_valid",
        "cold_flow_m3_h", "lmtd_value", "hot_in_c",
    }
    missing = sorted(required - set(records.columns))
    if missing:
        raise ValueError(f"Missing signal-recovery columns: {missing}")

    valid = records.loc[
        records.operating_valid.astype(bool)
        & records.ua_valid.astype(bool)
        & np.isfinite(records.ua_value)
        & (records.ua_value > 0)
    ].copy()
    valid["timestamp"] = pd.to_datetime(valid.timestamp)
    valid = valid.sort_values("timestamp").reset_index(drop=True)
    columns = [
        "event_id", "hx_id", "event_timestamp", "event_status", "event_confidence",
        "feasibility_status", "pre_valid_records", "post_valid_records",
        "pre_median_ua_kw_k", "post_median_ua_kw_k", "ua_recovery_fraction",
        "post_ua_cv", "flow_change_fraction", "lmtd_change_fraction",
        "hot_in_change_c", "stable_recovery", "operating_change_explains_recovery",
        "tam_proximity_days", "evidence_for", "evidence_against",
        "operating_condition_explanation", "cleaning_event_confirmed",
        "clean_condition_confirmed", "approval_status", "warning_code",
    ]
    if len(valid) < minimum_records * 2:
        return pd.DataFrame(columns=columns)

    tam = [pd.Timestamp(value, tz=valid.timestamp.dt.tz) if valid.timestamp.dt.tz is not None
           else pd.Timestamp(value) for value in (tam_dates or [])]

    def relative_change(before: pd.Series, after: pd.Series) -> float:
        a, b = float(before.median()), float(after.median())
        return np.nan if not np.isfinite(a) or a == 0 or not np.isfinite(b) else b / a - 1.0

    candidates: list[dict] = []
    for position in range(minimum_records, len(valid) - minimum_records + 1):
        pre = valid.iloc[max(0, position - pre_records):position]
        post = valid.iloc[position:min(len(valid), position + post_records)]
        if len(pre) < minimum_records or len(post) < minimum_records:
            continue
        pre_ua, post_ua = float(pre.ua_value.median()), float(post.ua_value.median())
        recovery = post_ua / pre_ua - 1.0
        if recovery < minimum_recovery_fraction:
            continue
        post_cv = float(post.ua_value.std(ddof=1) / post.ua_value.mean()) if len(post) > 1 else np.nan
        flow_change = relative_change(pre.cold_flow_m3_h, post.cold_flow_m3_h)
        lmtd_change = relative_change(pre.lmtd_value, post.lmtd_value)
        hot_change = float(post.hot_in_c.median() - pre.hot_in_c.median())
        stable = bool(np.isfinite(post_cv) and post_cv <= post_ua_cv_max)
        explained = bool(
            (np.isfinite(flow_change) and abs(flow_change) > flow_change_max_fraction)
            or (np.isfinite(lmtd_change) and abs(lmtd_change) > lmtd_change_max_fraction)
            or (np.isfinite(hot_change) and abs(hot_change) > hot_in_change_max_c)
        )
        evidence_window = pd.concat([pre, post]).sort_values("timestamp")
        ua_step = evidence_window.ua_value.diff()
        event_time = evidence_window.loc[ua_step.idxmax(), "timestamp"] if ua_step.max() > 0 else post.timestamp.iloc[0]
        tam_distance = min((abs((event_time - value).total_seconds()) / 86400 for value in tam), default=np.nan)
        near_tam = bool(np.isfinite(tam_distance) and tam_distance <= 7)
        if not stable or explained:
            status = "REJECTED_SIGNAL_EVENT"
        elif near_tam:
            status = "TAM_ASSOCIATED_RECOVERY"
        elif feasibility == "SWAP_CAPABLE":
            status = "BYPASS_OR_SWITCH_CANDIDATE"
        elif feasibility in {"ONLINE_FULL", "ONLINE_PARTIAL"}:
            status = "CLEANING_CANDIDATE"
        else:
            status = "UNEXPLAINED_RECOVERY"
        if status == "REJECTED_SIGNAL_EVENT":
            confidence = "LOW_SIGNAL_CONFIDENCE"
        elif recovery >= high_confidence_recovery_fraction and len(pre) >= pre_records and len(post) >= post_records:
            confidence = "HIGH_SIGNAL_CONFIDENCE"
        else:
            confidence = "MEDIUM_SIGNAL_CONFIDENCE"
        evidence_for = [f"Sustained median UA step recovery of {recovery:.1%}."]
        if stable:
            evidence_for.append(f"Post-event UA CV {post_cv:.3f} is within the screening limit.")
        evidence_against = []
        if explained:
            evidence_against.append("Concurrent flow, LMTD, or hot-inlet change can explain the apparent recovery.")
        if not stable:
            evidence_against.append("Post-event UA is not sufficiently stable.")
        if feasibility == "TAM_ONLY" and not near_tam:
            evidence_against.append("HX is TAM_ONLY; an online cleaning interpretation is infeasible.")
        candidates.append({
            "event_id": f"{hx_id}-{event_time.strftime('%Y%m%d')}", "hx_id": hx_id,
            "event_timestamp": event_time, "event_status": status,
            "event_confidence": confidence, "feasibility_status": feasibility,
            "pre_valid_records": len(pre), "post_valid_records": len(post),
            "pre_median_ua_kw_k": pre_ua, "post_median_ua_kw_k": post_ua,
            "ua_recovery_fraction": recovery, "post_ua_cv": post_cv,
            "flow_change_fraction": flow_change, "lmtd_change_fraction": lmtd_change,
            "hot_in_change_c": hot_change, "stable_recovery": stable,
            "operating_change_explains_recovery": explained,
            "tam_proximity_days": tam_distance,
            "evidence_for": " | ".join(evidence_for),
            "evidence_against": " | ".join(evidence_against),
            "operating_condition_explanation": (
                "Apparent recovery is condition-confounded." if explained
                else "No screened flow, LMTD, or hot-inlet step exceeds the configured limit."
            ),
            "cleaning_event_confirmed": False, "clean_condition_confirmed": False,
            "approval_status": "CANDIDATE",
            "warning_code": "NO_MAINTENANCE_EVIDENCE",
        })

    if not candidates:
        return pd.DataFrame(columns=columns)
    detected = pd.DataFrame(candidates).sort_values("ua_recovery_fraction", ascending=False)
    kept: list[int] = []
    for index, row in detected.iterrows():
        if all(abs((row.event_timestamp - detected.loc[other, "event_timestamp"]).days) > cluster_days
               for other in kept):
            kept.append(index)
    return detected.loc[kept].sort_values("event_timestamp").reset_index(drop=True)[columns]
