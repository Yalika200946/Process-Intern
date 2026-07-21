import pandas as pd
import pytest

from pipeline.explore_empirical_relative_performance import (
    calculate_relative_performance,
    relationship_summary,
)


def test_empirical_reference_preserves_above_reference_values_and_metadata():
    frame=pd.DataFrame({"timestamp":pd.date_range("2024-06-15",periods=7,tz="Asia/Bangkok"),"hx_id":"HX","operating_valid":[True]*7,"ua_valid":[True]*7,"ua_value":[10.,10.,10.,10.,10.,12.,8.],"ua_w_m2_k":[100.,100.,100.,100.,100.,120.,80.]})
    result,summary=calculate_relative_performance(frame,{"hx_id":"HX","start":"2024-06-15","end":"2024-06-19","reference_status":"HIGH_PERFORMANCE_POST_TAM_REFERENCE"})
    assert result.loc[5,"relative_ua_empirical"]==1.2
    assert result.loc[5,"relative_performance_loss"]==pytest.approx(-0.2)
    assert result.loc[5,"empirical_reference_warning_code"]=="ABOVE_EMPIRICAL_REFERENCE"
    assert not result.cleaning_event_confirmed.any() and not result.clean_condition_confirmed.any()
    assert summary["impact_status"]=="BLOCKED_BY_REFERENCE_SEMANTICS"


def test_empirical_reference_excludes_invalid_and_nonpositive_records():
    frame=pd.DataFrame({"timestamp":pd.date_range("2024-06-15",periods=7,tz="Asia/Bangkok"),"hx_id":"HX","operating_valid":[True,True,False,True,True,True,True],"ua_valid":[True]*7,"ua_value":[10.,10.,999.,0.,10.,12.,8.],"ua_w_m2_k":[100.]*7})
    result,summary=calculate_relative_performance(frame,{"hx_id":"HX","start":"2024-06-15","end":"2024-06-21","reference_status":"HIGH_PERFORMANCE_POST_TAM_REFERENCE"})
    assert summary["empirical_reference_valid_records"] == 5
    assert summary["reference_ua_empirical"] == 10.0
    assert 999.0 not in result.ua_value.to_list()


def test_insufficient_reference_data_is_reported_not_fabricated():
    frame=pd.DataFrame({"timestamp":pd.date_range("2024-06-15",periods=4,tz="Asia/Bangkok"),"hx_id":"HX","operating_valid":[True]*4,"ua_valid":[True]*4,"ua_value":[10.]*4,"ua_w_m2_k":[100.]*4})
    result,summary=calculate_relative_performance(frame,{"hx_id":"HX","start":"2024-06-15","end":"2024-06-18","reference_status":"HIGH_PERFORMANCE_POST_TAM_REFERENCE"})
    assert result.empty
    assert summary["empirical_reference_warning_code"] == "INSUFFICIENT_REFERENCE_DATA"


def test_relationship_summary_includes_time_and_valid_counts():
    frame=pd.DataFrame({"timestamp":pd.date_range("2024-06-15",periods=6,tz="Asia/Bangkok"),"hx_id":"HX","cold_flow_m3_h":range(6),"lmtd_value":range(10,16),"hot_in_c":range(100,106),"relative_performance_loss":[.5,.4,.3,.2,.1,0.]})
    result=relationship_summary(frame)
    assert set(result.x_variable) == {"cold_flow_m3_h","lmtd_value","hot_in_c","time_days"}
    assert (result.valid_sample_count == 6).all()


def test_output_names_do_not_claim_clean_or_confirmed_fouling():
    frame=pd.DataFrame({"timestamp":pd.date_range("2024-06-15",periods=5,tz="Asia/Bangkok"),"hx_id":"HX","operating_valid":[True]*5,"ua_valid":[True]*5,"ua_value":[10.]*5,"ua_w_m2_k":[100.]*5})
    result,_=calculate_relative_performance(frame,{"hx_id":"HX","start":"2024-06-15","end":"2024-06-19","reference_status":"HIGH_PERFORMANCE_POST_TAM_REFERENCE"})
    forbidden={"clean_ua","ua_normalized","fouling_index","normalized_clean_ua","confirmed_fouling_index","confirmed_fouling_loss"}
    assert forbidden.isdisjoint(result.columns)
    assert {"reference_ua_empirical","relative_ua_empirical","relative_performance_loss"}.issubset(result.columns)
