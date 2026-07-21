import pandas as pd

from pipeline.build_mvp_coverage_outputs import correlation_summary, data_quality_summary, method_recommendations


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
