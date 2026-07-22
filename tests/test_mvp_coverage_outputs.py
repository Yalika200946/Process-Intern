import pandas as pd

from pipeline.build_mvp_coverage_outputs import (
    correlation_summary, data_quality_summary, method_recommendations,
    performance_summary, temporal_quality_audit,
)


def test_quality_summary_counts_all_states_and_warnings():
    states=pd.DataFrame({"hx_id":["HX"]*3,"operating_state":["STEADY","TRANSIENT","INVALID_SENSOR"],"quality_warning_code":["","TRANSIENT_OPERATION","SENSOR_FLATLINE|MAP_WARNING"]})
    summary,warnings=data_quality_summary(states)
    assert summary.loc[0,"total_records"]==3
    assert set(warnings.warning)=={"TRANSIENT_OPERATION","SENSOR_FLATLINE","MAP_WARNING"}


def test_relationship_outputs_use_valid_records_and_are_review_only():
    physics=pd.DataFrame({"hx_id":["HX"]*4,"operating_valid":[True,True,False,True],"ua_valid":[True,True,False,True],"q_cold_value":[1.,2.,999.,3.],"cold_flow_m3_h":[10.,20.,999.,30.],"cold_in_c":[1.,1.,1.,1.],"cold_out_c":[2.,3.,999.,4.],"ua_w_m2_k":[4.,5.,999.,6.],"lmtd_value":[10.,11.,999.,12.],"hot_in_c":[100.,101.,999.,102.],"sg_15_6c":[.8,.81,.99,.82]})
    correlations=correlation_summary(physics,minimum=3)
    assert (correlations.paired_records==3).all()
    settings={"minimum_valid_coverage_for_method_review":.5,"strong_absolute_correlation":.5}
    rec=method_recommendations(physics,correlations,settings)
    assert rec.loc[0,"approval_status"]=="REVIEW_ONLY_NOT_A_CLEAN_BASELINE"
    assert set(["clean_ua","fouling_index","cit_gain"]).isdisjoint(rec.columns)


def test_temporal_audit_reports_duplicates_gaps_and_no_interpolation():
    states=pd.DataFrame({"hx_id":["HX"]*4,"timestamp":pd.to_datetime(["2024-01-01","2024-01-01","2024-01-02","2024-01-05"],utc=True),"quality_warning_code":["","","SENSOR_FLATLINE",""]})
    summary,gaps=temporal_quality_audit(states,long_gap_hours=36)
    assert summary.loc[0,"duplicate_timestamp_records"]==2
    assert summary.loc[0,"long_gap_count"]==1
    assert summary.loc[0,"flatline_record_count"]==1
    assert not summary.loc[0,"long_gap_interpolation_used"]
    assert gaps.loc[0,"gap_hours"]==72


def test_performance_summary_uses_only_valid_records():
    physics=pd.DataFrame({"hx_id":["HX"]*3,"operating_valid":[True,False,True],"ua_valid":[True,False,True],"q_cold_value":[10,999,20],"lmtd_value":[5,999,7],"ua_w_m2_k":[100,999,120]})
    out=performance_summary(physics)
    assert out.loc[0,"valid_records"]==2
    assert out.loc[0,"median_q_cold"]==15
