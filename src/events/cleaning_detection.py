"""Signal-inferred cleaning candidates without claiming maintenance confirmation."""

from __future__ import annotations

import numpy as np
import pandas as pd


def detect_plant_tam_windows(
    timestamps,
    total_charge_m3_h,
    *,
    flow_threshold_m3_h: float = 50.0,
    minimum_consecutive_records: int = 3,
    source_status: str = "SIGNAL_DERIVED_TAM",
) -> pd.DataFrame:
    """Detect plant-level low-total-charge intervals without inferring HX cleaning."""
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime(timestamps),
        "total_charge_m3_h": pd.to_numeric(total_charge_m3_h, errors="coerce"),
    }).dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    low = frame.total_charge_m3_h.notna() & (frame.total_charge_m3_h < flow_threshold_m3_h)
    runs = low.ne(low.shift(fill_value=False)).cumsum()
    rows = []
    for _, group in frame[low].groupby(runs[low]):
        if len(group) < minimum_consecutive_records:
            continue
        last_index = int(group.index[-1])
        later = frame.loc[last_index + 1:]
        restart = later.loc[
            later.total_charge_m3_h.notna()
            & (later.total_charge_m3_h >= flow_threshold_m3_h), "timestamp"
        ]
        number = len(rows) + 1
        rows.append({
            "tam_id": f"TAM_{group.timestamp.iloc[0].year}",
            "tam_start": group.timestamp.iloc[0],
            "tam_end": group.timestamp.iloc[-1],
            "restart_from": restart.iloc[0] if not restart.empty else pd.NaT,
            "low_flow_record_count": len(group),
            "minimum_total_charge_m3_h": float(group.total_charge_m3_h.min()),
            "median_total_charge_m3_h": float(group.total_charge_m3_h.median()),
            "flow_threshold_m3_h": flow_threshold_m3_h,
            "tam_sequence": number,
            "plant_tam_status": source_status,
            "plant_tam_confirmed_by_signal": True,
            "individual_hx_cleaning_confirmed": False,
            "interpretation": "Plant-level low-total-charge interval; individual HX cleaning is not confirmed.",
        })
    return pd.DataFrame(rows)


def review_hx_tam_recovery(
    records: pd.DataFrame,
    tam_event: dict,
    *,
    comparison_window_days: int = 30,
    minimum_valid_records: int = 7,
    recovery_threshold_fraction: float = 0.05,
    persistence_days: list[int] = (30, 60, 90),
    flow_change_max_fraction: float = 0.10,
    lmtd_change_max_fraction: float = 0.10,
    hot_in_change_max_c: float = 5.0,
    matched_review_config: dict | None = None,
) -> dict:
    """Review one HX around a plant TAM; never confirms an individual cleaning."""
    hx_id = str(records.hx_id.iloc[0]) if not records.empty and "hx_id" in records else "UNKNOWN"
    start = pd.Timestamp(tam_event["tam_start"])
    restart = pd.Timestamp(tam_event["restart_from"])
    valid = records.loc[
        records.operating_valid.astype(bool)
        & records.ua_valid.astype(bool)
        & np.isfinite(records.ua_value)
        & (records.ua_value > 0)
    ].copy()
    valid["timestamp"] = pd.to_datetime(valid.timestamp)
    pre = valid[(valid.timestamp >= start - pd.Timedelta(days=comparison_window_days)) & (valid.timestamp < start)]
    post = valid[(valid.timestamp >= restart) & (valid.timestamp < restart + pd.Timedelta(days=comparison_window_days))]

    def median_change(column: str) -> float:
        a, b = pre[column].median(), post[column].median()
        return float(b / a - 1) if np.isfinite(a) and a != 0 and np.isfinite(b) else np.nan

    pre_ua, post_ua = pre.ua_value.median(), post.ua_value.median()
    recovery = float(post_ua / pre_ua - 1) if np.isfinite(pre_ua) and pre_ua > 0 and np.isfinite(post_ua) else np.nan
    flow_change = median_change("cold_flow_m3_h")
    lmtd_change = median_change("lmtd_value")
    hot_change = float(post.hot_in_c.median() - pre.hot_in_c.median()) if len(pre) and len(post) else np.nan
    confounded = bool(
        (np.isfinite(flow_change) and abs(flow_change) > flow_change_max_fraction)
        or (np.isfinite(lmtd_change) and abs(lmtd_change) > lmtd_change_max_fraction)
        or (np.isfinite(hot_change) and abs(hot_change) > hot_in_change_max_c)
    )
    persistence = {}
    for days in persistence_days:
        window = valid[(valid.timestamp >= restart) & (valid.timestamp < restart + pd.Timedelta(days=days))]
        value = window.ua_value.median()
        persistence[f"post_{days}d_valid_records"] = len(window)
        persistence[f"post_{days}d_ua_recovery_fraction"] = (
            float(value / pre_ua - 1) if np.isfinite(pre_ua) and pre_ua > 0 and np.isfinite(value) else np.nan
        )
    matched = matched_condition_review(records, restart, **(matched_review_config or {}))
    enough = len(pre) >= minimum_valid_records and len(post) >= minimum_valid_records
    if not enough or pd.isna(restart):
        status = "TAM_ASSOCIATED_INSUFFICIENT_DATA"
    elif confounded:
        status = "TAM_ASSOCIATED_CONDITION_CONFOUNDED"
    elif recovery >= recovery_threshold_fraction and matched["matched_review_status"] == "MATCHED_RECOVERY_PLAUSIBLE":
        status = "TAM_ASSOCIATED_RECOVERY"
    else:
        status = "TAM_ASSOCIATED_NO_CLEAR_RECOVERY"
    return {
        "tam_id": tam_event["tam_id"], "hx_id": hx_id,
        "tam_start": start, "tam_end": pd.Timestamp(tam_event["tam_end"]), "restart_from": restart,
        "pre_valid_records": len(pre), "post_valid_records": len(post),
        "pre_median_ua_kw_k": pre_ua, "post_median_ua_kw_k": post_ua,
        "apparent_ua_recovery_fraction": recovery,
        "flow_change_fraction": flow_change, "lmtd_change_fraction": lmtd_change,
        "hot_in_change_c": hot_change, "operating_condition_confounding": confounded,
        "configuration_consistency_status": "UNAVAILABLE_NO_CONFIGURATION_TAG",
        "tam_recovery_status": status,
        **matched, **persistence,
        "plant_tam_status": tam_event["plant_tam_status"],
        "hx_exposed_to_tam": True,
        "hx_performance_recovery_observed": status == "TAM_ASSOCIATED_RECOVERY",
        "individual_hx_cleaning_confirmed": False,
        "clean_condition_confirmed": False,
        "warning_code": "NO_INDIVIDUAL_HX_MAINTENANCE_EVIDENCE",
        "interpretation": "TAM-associated HX performance review; not a confirmed individual cleaning event.",
    }


def consolidate_cross_hx_events(
    events: pd.DataFrame,
    *,
    cluster_days: int = 3,
    multi_hx_process_signal_minimum: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Group coincident HX signals without claiming one cleaning per HX."""
    if events.empty:
        return events.copy(), pd.DataFrame()
    out = events.copy()
    out["event_timestamp"] = pd.to_datetime(out.event_timestamp)
    ordered = out.sort_values("event_timestamp")
    group_number = 0
    last_time = None
    assignments = {}
    for index, row in ordered.iterrows():
        if last_time is None or row.event_timestamp - last_time > pd.Timedelta(days=cluster_days):
            group_number += 1
        assignments[index] = group_number
        last_time = row.event_timestamp
    out["event_group_number"] = pd.Series(assignments)
    out["event_group_id"] = out.event_group_number.map(lambda value: f"SIGNAL_GROUP_{int(value):03d}")

    group_rows = []
    for group_id, group in out.groupby("event_group_id", sort=False):
        hx_count = int(group.hx_id.nunique())
        statuses = set(group.event_status)
        if "TAM_ASSOCIATED_RECOVERY" in statuses:
            classification = "PLANT_TAM_RESTART_SIGNAL"
        elif hx_count >= multi_hx_process_signal_minimum:
            classification = "MULTI_HX_PROCESS_DISTURBANCE"
        elif hx_count == 2:
            classification = "SHARED_PROCESS_OR_MAINTENANCE_SIGNAL"
        else:
            classification = "INDIVIDUAL_HX_SIGNAL"
        group_rows.append({
            "event_group_id": group_id,
            "group_start": group.event_timestamp.min(), "group_end": group.event_timestamp.max(),
            "hx_count": hx_count, "hx_ids": "|".join(sorted(group.hx_id.unique())),
            "raw_signal_count": len(group),
            "candidate_signal_count": int(group.event_status.isin([
                "CLEANING_CANDIDATE", "BYPASS_OR_SWITCH_CANDIDATE", "TAM_ASSOCIATED_RECOVERY"
            ]).sum()),
            "group_classification": classification,
            "confirmed_independent_cleaning_action_count": 0,
            "cleaning_event_confirmed": False,
            "warning_code": "CROSS_HX_GROUP_REQUIRES_ENGINEERING_REVIEW",
        })
    groups = pd.DataFrame(group_rows)
    out = out.merge(groups[["event_group_id", "hx_count", "group_classification"]],
                    on="event_group_id", how="left", suffixes=("", "_group"))

    def evidence_level(row) -> str:
        if row.event_status == "REJECTED_SIGNAL_EVENT":
            return "REJECTED"
        if row.group_classification == "MULTI_HX_PROCESS_DISTURBANCE":
            return "PROCESS_CHANGE_LIKELY"
        return {
            "NOT_CLEANING_ELIGIBLE_MID_RUN": "INFEASIBLE_MID_RUN_SIGNAL",
            "TAM_ASSOCIATED_RECOVERY": "TAM_ASSOCIATED_RECOVERY",
            "BYPASS_OR_SWITCH_CANDIDATE": "SHELL_SWITCH_OR_BYPASS_CANDIDATE",
            "CLEANING_CANDIDATE": "CLEANING_CANDIDATE",
        }.get(row.event_status, "UNRESOLVED_SIGNAL")

    out["evidence_level"] = out.apply(evidence_level, axis=1)
    out["independent_cleaning_event_confirmed"] = False
    return out.drop(columns="event_group_number"), groups


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
            status = "NOT_CLEANING_ELIGIBLE_MID_RUN"
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


def matched_condition_review(
    records: pd.DataFrame,
    event_timestamp,
    *,
    window_records: int = 60,
    minimum_pairs: int = 7,
    flow_tolerance_fraction: float = 0.05,
    lmtd_tolerance_fraction: float = 0.05,
    hot_in_tolerance_c: float = 3.0,
    recovery_threshold_fraction: float = 0.05,
    recovery_iqr_max: float = 0.15,
) -> dict:
    """Compare post-event UA with nearest pre-event operating-condition matches.

    Matching is retrospective and descriptive. A positive result raises an event
    to an engineering-review queue; it does not confirm cleaning or a clean state.
    """
    frame = records.loc[
        records.operating_valid.astype(bool)
        & records.ua_valid.astype(bool)
        & np.isfinite(records.ua_value)
        & (records.ua_value > 0)
    ].copy()
    frame["timestamp"] = pd.to_datetime(frame.timestamp)
    event_time = pd.Timestamp(event_timestamp)
    pre = frame[frame.timestamp < event_time].tail(window_records).reset_index(drop=True)
    post = frame[frame.timestamp >= event_time].head(window_records).reset_index(drop=True)
    used: set[int] = set()
    pairs: list[tuple[float, float]] = []
    for post_row in post.itertuples():
        eligible = []
        for index, pre_row in pre.iterrows():
            if index in used:
                continue
            if not all(np.isfinite([pre_row.cold_flow_m3_h, post_row.cold_flow_m3_h,
                                    pre_row.lmtd_value, post_row.lmtd_value,
                                    pre_row.hot_in_c, post_row.hot_in_c])):
                continue
            flow_delta = abs(post_row.cold_flow_m3_h / pre_row.cold_flow_m3_h - 1) if pre_row.cold_flow_m3_h else np.inf
            lmtd_delta = abs(post_row.lmtd_value / pre_row.lmtd_value - 1) if pre_row.lmtd_value else np.inf
            hot_delta = abs(post_row.hot_in_c - pre_row.hot_in_c)
            if flow_delta <= flow_tolerance_fraction and lmtd_delta <= lmtd_tolerance_fraction and hot_delta <= hot_in_tolerance_c:
                distance = flow_delta / flow_tolerance_fraction + lmtd_delta / lmtd_tolerance_fraction + hot_delta / hot_in_tolerance_c
                eligible.append((distance, index, float(pre_row.ua_value)))
        if eligible:
            _, index, pre_ua = min(eligible)
            used.add(index)
            pairs.append((pre_ua, float(post_row.ua_value)))
    if len(pairs) < minimum_pairs:
        return {
            "matched_review_status": "INSUFFICIENT_MATCHED_DATA", "matched_pair_count": len(pairs),
            "matched_median_recovery_fraction": None, "matched_recovery_iqr": None,
            "matched_condition_cleaning_confirmed": False,
        }
    recoveries = pd.Series([post_ua / pre_ua - 1 for pre_ua, post_ua in pairs])
    median = float(recoveries.median())
    recovery_iqr = float(recoveries.quantile(.75) - recoveries.quantile(.25))
    if median < recovery_threshold_fraction:
        status = "NO_MATCHED_RECOVERY"
    elif recovery_iqr > recovery_iqr_max:
        status = "MATCHED_RECOVERY_UNSTABLE"
    else:
        status = "MATCHED_RECOVERY_PLAUSIBLE"
    return {
        "matched_review_status": status, "matched_pair_count": len(pairs),
        "matched_median_recovery_fraction": median,
        "matched_recovery_iqr": recovery_iqr,
        "matched_condition_cleaning_confirmed": False,
    }
