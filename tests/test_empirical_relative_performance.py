import pandas as pd
import pytest

from pipeline.explore_empirical_relative_performance import calculate_relative_performance


def test_empirical_reference_preserves_above_reference_values_and_metadata():
    frame=pd.DataFrame({"timestamp":pd.date_range("2024-06-15",periods=6,tz="Asia/Bangkok"),"hx_id":"HX","operating_valid":[True]*6,"ua_valid":[True]*6,"ua_value":[10.,10.,10.,12.,8.,10.],"ua_w_m2_k":[100.,100.,100.,120.,80.,100.]})
    result,summary=calculate_relative_performance(frame,{"hx_id":"HX","start":"2024-06-15","end":"2024-06-17","reference_status":"HIGH_PERFORMANCE_POST_TAM_REFERENCE"})
    assert result.loc[3,"relative_ua"]==1.2
    assert result.loc[3,"relative_performance_loss"]==pytest.approx(-0.2)
    assert result.loc[3,"relative_warning_code"]=="ABOVE_REFERENCE_PERFORMANCE"
    assert not result.cleaning_event_confirmed.any() and not result.clean_condition_confirmed.any()
    assert summary["impact_status"]=="BLOCKED_BY_REFERENCE_SEMANTICS"


def test_output_names_do_not_claim_clean_or_confirmed_fouling():
    frame=pd.DataFrame({"timestamp":pd.date_range("2024-06-15",periods=5,tz="Asia/Bangkok"),"hx_id":"HX","operating_valid":[True]*5,"ua_valid":[True]*5,"ua_value":[10.]*5,"ua_w_m2_k":[100.]*5})
    result,_=calculate_relative_performance(frame,{"hx_id":"HX","start":"2024-06-15","end":"2024-06-19","reference_status":"HIGH_PERFORMANCE_POST_TAM_REFERENCE"})
    forbidden={"clean_ua","normalized_clean_ua","confirmed_fouling_index","confirmed_fouling_loss"}
    assert forbidden.isdisjoint(result.columns)
