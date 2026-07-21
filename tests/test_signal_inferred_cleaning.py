import pandas as pd
import pytest

from src.events.cleaning_detection import (
    detect_plant_tam_windows, detect_signal_recoveries, matched_condition_review,
    review_hx_tam_recovery,
)


def fixture(*, flow_after=100.0, lmtd_after=30.0, ua_after=110.0):
    timestamps = pd.date_range("2024-01-01", periods=40, tz="Asia/Bangkok")
    return pd.DataFrame({
        "timestamp": timestamps,
        "ua_value": [100.0] * 20 + [ua_after] * 20,
        "operating_valid": True,
        "ua_valid": True,
        "cold_flow_m3_h": [100.0] * 20 + [flow_after] * 20,
        "lmtd_value": [30.0] * 20 + [lmtd_after] * 20,
        "hot_in_c": 150.0,
    })


def test_sustained_recovery_is_candidate_but_never_confirmed():
    result = detect_signal_recoveries(fixture(), hx_id="HX", feasibility="ONLINE_FULL")
    event = result.loc[result.event_status == "CLEANING_CANDIDATE"].iloc[0]
    assert event.ua_recovery_fraction == pytest.approx(0.10)
    assert event.event_timestamp == pd.Timestamp("2024-01-21", tz="Asia/Bangkok")
    assert not event.cleaning_event_confirmed
    assert not event.clean_condition_confirmed
    assert event.warning_code == "NO_MAINTENANCE_EVIDENCE"


def test_operating_change_rejects_apparent_recovery():
    result = detect_signal_recoveries(
        fixture(flow_after=130.0), hx_id="HX", feasibility="ONLINE_FULL"
    )
    assert (result.event_status == "REJECTED_SIGNAL_EVENT").any()
    assert result.operating_change_explains_recovery.any()


def test_tam_only_midrun_recovery_is_unexplained_not_cleaning_candidate():
    result = detect_signal_recoveries(fixture(), hx_id="HX", feasibility="TAM_ONLY")
    assert "NOT_CLEANING_ELIGIBLE_MID_RUN" in set(result.event_status)
    assert "CLEANING_CANDIDATE" not in set(result.event_status)


def test_invalid_records_are_excluded_from_pre_post_evidence():
    frame = fixture()
    frame.loc[0:9, "operating_valid"] = False
    frame.loc[10, "ua_value"] = float("nan")
    result = detect_signal_recoveries(frame, hx_id="HX", feasibility="ONLINE_FULL")
    assert not result.empty
    assert (result.pre_valid_records <= 14).all()


def test_tam_proximity_is_association_not_confirmed_cleaning():
    result = detect_signal_recoveries(
        fixture(), hx_id="HX", feasibility="TAM_ONLY", tam_dates=["2024-01-21"]
    )
    event = result.loc[result.event_status == "TAM_ASSOCIATED_RECOVERY"].iloc[0]
    assert not event.cleaning_event_confirmed
    assert event.approval_status == "CANDIDATE"


def test_matched_condition_review_recovers_step_without_confirmation():
    result = matched_condition_review(fixture(), pd.Timestamp("2024-01-21", tz="Asia/Bangkok"))
    assert result["matched_review_status"] == "MATCHED_RECOVERY_PLAUSIBLE"
    assert result["matched_median_recovery_fraction"] == pytest.approx(0.10)
    assert not result["matched_condition_cleaning_confirmed"]


def test_matched_condition_review_reports_insufficient_overlap():
    result = matched_condition_review(
        fixture(flow_after=150.0), pd.Timestamp("2024-01-21", tz="Asia/Bangkok")
    )
    assert result["matched_review_status"] == "INSUFFICIENT_MATCHED_DATA"


def test_matched_condition_review_rejects_unstable_recovery_distribution():
    frame = fixture()
    frame.loc[20:, "ua_value"] = [80.0, 140.0] * 10
    result = matched_condition_review(
        frame, pd.Timestamp("2024-01-21", tz="Asia/Bangkok"), recovery_iqr_max=0.15
    )
    assert result["matched_review_status"] == "MATCHED_RECOVERY_UNSTABLE"


def test_total_charge_detects_two_tam_intervals_and_restart():
    dates = pd.date_range("2021-01-01", periods=12, tz="Asia/Bangkok")
    flow = [500, 500, 10, 5, 0, 500, 500, 40, 30, 20, 10, 500]
    result = detect_plant_tam_windows(dates, flow, minimum_consecutive_records=3)
    assert len(result) == 2
    assert result.iloc[0].tam_start == dates[2]
    assert result.iloc[0].tam_end == dates[4]
    assert result.iloc[0].restart_from == dates[5]
    assert not result.individual_hx_cleaning_confirmed.any()


def test_short_low_flow_upset_is_not_tam():
    dates = pd.date_range("2021-01-01", periods=5, tz="Asia/Bangkok")
    result = detect_plant_tam_windows(dates, [500, 10, 10, 500, 500], minimum_consecutive_records=3)
    assert result.empty


def test_tam_hx_recovery_is_observed_but_cleaning_unconfirmed():
    frame = fixture()
    frame["hx_id"] = "HX"
    event = {"tam_id": "TAM_2024", "tam_start": pd.Timestamp("2024-01-18", tz="Asia/Bangkok"),
             "tam_end": pd.Timestamp("2024-01-20", tz="Asia/Bangkok"),
             "restart_from": pd.Timestamp("2024-01-21", tz="Asia/Bangkok"),
             "plant_tam_status": "SIGNAL_DERIVED_TAM"}
    result = review_hx_tam_recovery(frame, event, comparison_window_days=20)
    assert result["tam_recovery_status"] == "TAM_ASSOCIATED_RECOVERY"
    assert result["apparent_ua_recovery_fraction"] == pytest.approx(0.10)
    assert not result["individual_hx_cleaning_confirmed"]


def test_tam_hx_review_flags_operating_condition_confounding():
    frame = fixture(flow_after=130.0)
    frame["hx_id"] = "HX"
    event = {"tam_id": "TAM_2024", "tam_start": pd.Timestamp("2024-01-18", tz="Asia/Bangkok"),
             "tam_end": pd.Timestamp("2024-01-20", tz="Asia/Bangkok"),
             "restart_from": pd.Timestamp("2024-01-21", tz="Asia/Bangkok"),
             "plant_tam_status": "SIGNAL_DERIVED_TAM"}
    result = review_hx_tam_recovery(frame, event, comparison_window_days=20)
    assert result["tam_recovery_status"] == "TAM_ASSOCIATED_CONDITION_CONFOUNDED"


def test_tam_hx_review_reports_insufficient_valid_data():
    frame = fixture()
    frame["hx_id"] = "HX"
    frame.loc[:34, "operating_valid"] = False
    event = {"tam_id": "TAM_2024", "tam_start": pd.Timestamp("2024-01-18", tz="Asia/Bangkok"),
             "tam_end": pd.Timestamp("2024-01-20", tz="Asia/Bangkok"),
             "restart_from": pd.Timestamp("2024-01-21", tz="Asia/Bangkok"),
             "plant_tam_status": "SIGNAL_DERIVED_TAM"}
    result = review_hx_tam_recovery(frame, event, comparison_window_days=20)
    assert result["tam_recovery_status"] == "TAM_ASSOCIATED_INSUFFICIENT_DATA"
