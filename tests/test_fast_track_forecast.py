import pandas as pd
import pytest
from pipeline.forecast_empirical_performance import linear_forecast

def test_linear_forecast_uses_empirical_semantics_and_blocks_unapproved_threshold():
    n=100;frame=pd.DataFrame({"hx_id":"HX","timestamp":pd.date_range("2024-01-01",periods=n,tz="Asia/Bangkok"),"relative_ua_empirical":[1-i*.001 for i in range(n)]})
    forecast,summary=linear_forecast(frame,lookback=100,horizons=(30,))
    assert forecast.iloc[0].relative_ua_forecast==pytest.approx(.871)
    assert forecast.iloc[0].status=="EXPLORATORY"
    assert summary["condition_threshold_status"]=="BLOCKED"
    assert not forecast.iloc[0].clean_condition_confirmed

def test_forecast_reports_insufficient_recent_records():
    frame=pd.DataFrame({"hx_id":"HX","timestamp":pd.date_range("2024-01-01",periods=10,tz="Asia/Bangkok"),"relative_ua_empirical":1.0})
    forecast,summary=linear_forecast(frame)
    assert forecast.empty and summary["status"]=="PARTIAL"
