import pandas as pd

from src.validation.real_data import classify_hx_records, mapped_series


def _config():
    return {"aliases":{"FLOW":"flow.pv"},"rules":{"flow_min_m3_h":15.0,"cold_delta_t_min_c":3.0,"hot_delta_t_min_c":2.0,"terminal_delta_t_min_c":2.0,"temperature_min_c":0.0,"temperature_max_c":450.0,"startup_records":2,"steady_flow_relative_change_max":0.10,"steady_temperature_change_max_c":5.0,"long_gap_hours":36.0,"flatline_records":7}}


def _frame():
    return pd.DataFrame({"timestamp":pd.date_range("2025-01-01",periods=5,tz="Asia/Bangkok"),"flow.pv":[0,100,101,102,102],"ci":[40,40,40,40,40],"co":[80,80,80,80,80],"hi":[130,130,130,130,130],"ho":[95,95,95,95,95]})


def _hx():
    return {"status":"READY","cold_flow":"FLOW","cold_in":"ci","cold_out":"co","hot_in":"hi","hot_out":"ho"}


def test_alias_and_calculated_and_inferred_mapping_are_explicit():
    frame=_frame(); values,kind,tags=mapped_series(frame,"FLOW",_config()["aliases"])
    assert kind=="MEASURED" and tags==["flow.pv"] and values.iloc[1]==100
    summed,kind,_=mapped_series(frame,{"method":"sum","tags":["ci","co"]},{})
    inferred,inferred_kind,_=mapped_series(frame,{"method":"row_max","tags":["ci","co"]},{})
    assert kind=="CALCULATED" and summed.iloc[0]==120
    assert inferred_kind=="INFERRED" and inferred.iloc[0]==80


def test_operating_states_are_rule_based_and_limited_to_contract():
    result=classify_hx_records(_frame(),"HX",_hx(),_config())
    assert result.operating_state.tolist()==["SHUTDOWN","STARTUP","STARTUP","STEADY","STEADY"]
    assert set(result.operating_state)<=set(["SHUTDOWN","STARTUP","STEADY","TRANSIENT","INVALID_SENSOR","UNAVAILABLE"])
    assert result.operating_valid.tolist()==[False,False,False,True,True]


def test_impossible_temperature_relationship_is_retained_and_invalid():
    frame=_frame();frame.loc[4,"ho"]=30
    result=classify_hx_records(frame,"HX",_hx(),_config())
    assert result.loc[4,"operating_state"]=="INVALID_SENSOR"
    assert result.loc[4,"quality_warning_code"]=="IMPOSSIBLE_TEMPERATURE_RELATIONSHIP"


def test_blocked_and_unavailable_hx_return_explicit_unavailable_rows():
    for status,reason_key in [("BLOCKED","blocked_reason"),("UNAVAILABLE","unavailable_reason")]:
        hx={"status":status,reason_key:"TEST_REASON"}
        result=classify_hx_records(_frame(),"HX",hx,_config())
        assert (result.operating_state=="UNAVAILABLE").all()
        assert not result.operating_valid.any()
        assert (result.quality_warning_code=="TEST_REASON").all()


def test_long_gap_and_flatline_are_explicitly_invalid():
    frame=_frame(); frame.loc[4,"timestamp"] += pd.Timedelta(days=3)
    result=classify_hx_records(frame,"HX",_hx(),_config())
    assert result.loc[4,"quality_warning_code"]=="LONG_TIMESTAMP_GAP"
    frame=pd.concat([_frame().iloc[:1]]*7,ignore_index=True)
    frame["timestamp"]=pd.date_range("2025-01-01",periods=7,tz="Asia/Bangkok")
    frame["flow.pv"]=100
    result=classify_hx_records(frame,"HX",_hx(),_config())
    assert (result.quality_warning_code=="SENSOR_FLATLINE").all()
