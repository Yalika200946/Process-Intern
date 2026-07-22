import pandas as pd
from pipeline.build_fast_track_decision_support import build_priorities

def test_priority_never_promotes_candidate_to_final_recommendation():
    config={"heat_exchangers":{"HX":{"status":"READY"},"BAD":{"status":"BLOCKED"}}};coverage=pd.DataFrame({"ua_valid":{"HX":80,"BAD":0}});events=pd.DataFrame({"hx_id":["HX"],"evidence_level":["CLEANING_CANDIDATE"]});relative=pd.DataFrame({"timestamp":pd.to_datetime(["2024-01-01"]),"hx_id":["HX"],"relative_performance_loss":[.2]});forecast=pd.DataFrame({"hx_id":["HX"],"slope_relative_ua_per_day":[-.001]})
    out=build_priorities(config,coverage,events,relative,forecast)
    assert out.loc[out.hx_id=="HX","recommendation_status"].iloc[0]=="NEEDS_ENGINEERING_REVIEW"
    assert not out.final_cleaning_recommendation.any()
    assert out.loc[out.hx_id=="BAD","recommendation_status"].iloc[0]=="INSUFFICIENT_EVIDENCE"
