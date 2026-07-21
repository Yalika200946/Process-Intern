import pandas as pd

from pipeline.review_provisional_post_tam import assess_window


def _physics():
    dates=pd.date_range("2024-05-15",periods=90,tz="Asia/Bangkok")
    ua=[80.0]*31+[100.0]*14+[98.0]*45
    return pd.DataFrame({"timestamp":dates,"hx_id":"HX","operating_valid":True,"ua_valid":True,
                         "ua_w_m2_k":ua,"cold_flow_m3_h":100.0,"lmtd_value":40.0,
                         "cold_in_c":50.0,"cold_out_c":90.0,"hot_in_c":140.0,"hot_out_c":100.0,
                         "sg_15_6c":.85})


def _settings():
    return {"pre_review_days":30,"post_review_days":30,"sensitivity_inward_shift_days":[0,1,3]}


def test_review_is_provisional_and_has_no_fouling_or_cit_fields():
    row,sens=assess_window(_physics(),{"hx_id":"HX","start":"2024-06-15","end":"2024-06-28"},_settings())
    assert row["approval_status"]=="NOT_YET_APPROVED"
    assert row["reference_status"]=="PROVISIONAL_POST_TAM_REFERENCE"
    assert set(["fouling_index","ua_normalized","cit_gain","clean_ua"]).isdisjoint(row)
    assert (sens.status=="PROVISIONAL_SENSITIVITY_ONLY").all()


def test_provisional_median_uses_only_the_window_not_following_data():
    physics=_physics();spec={"hx_id":"HX","start":"2024-06-15","end":"2024-06-28"}
    row,_=assess_window(physics,spec,_settings())
    original=row["median_ua"]
    physics.loc[physics.timestamp>pd.Timestamp("2024-06-28",tz="Asia/Bangkok"),"ua_w_m2_k"]=9999
    changed,_=assess_window(physics,spec,_settings())
    assert changed["median_ua"]==original
    assert changed["post_window_median_ua"]!=row["post_window_median_ua"]
