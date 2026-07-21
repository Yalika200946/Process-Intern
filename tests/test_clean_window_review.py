import pandas as pd

from pipeline.review_clean_windows import propose_post_event_windows


def _physics():
    return pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=20, tz="Asia/Bangkok"),
        "hx_id": ["HX"] * 20, "operating_valid": [False, False] + [True] * 18,
        "ua_valid": [False, False] + [True] * 18,
        "ua_w_m2_k": [None, None] + list(range(100, 118)),
        "cold_flow_m3_h": [100] * 20, "cold_in_c": [40] * 20,
        "cold_out_c": [80] * 20, "hot_in_c": [130] * 20, "hot_out_c": [95] * 20,
    })


def test_candidate_window_never_approves_or_calculates_fouling_fields():
    evidence = pd.DataFrame({"hx_id":["HX"], "event_date":[pd.Timestamp("2025-01-01")],
                             "evidence_source":["test.csv"],
                             "evidence_class":["DETECTED_EVENT_SIGNAL"]})
    result = propose_post_event_windows(_physics(), evidence, min_records=14)
    assert result.loc[0, "status"] == "CANDIDATE"
    assert result.loc[0, "engineer_decision"] == "PENDING"
    forbidden = {"clean_ua", "ua_normalized", "fouling_index", "cit_gain"}
    assert forbidden.isdisjoint(result.columns)


def test_invalid_records_are_excluded_and_short_window_is_not_candidate():
    evidence = pd.DataFrame({"hx_id":["HX"], "event_date":[pd.Timestamp("2025-01-15")],
                             "evidence_source":["test.csv"],
                             "evidence_class":["CONFIRMED_TAM_CONTEXT"]})
    result = propose_post_event_windows(_physics(), evidence, min_records=14)
    assert result.loc[0, "valid_record_count"] == 5
    assert result.loc[0, "status"] == "INSUFFICIENT_VALID_RECORDS"
