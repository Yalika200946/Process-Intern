import numpy as np
import pandas as pd
from pipeline.screen_hx_cit_relationships import partial_correlation,screen_relationships

def fixture(hx="HX",n=100):
    t=pd.date_range("2024-01-01",periods=n,tz="Asia/Bangkok");flow=np.linspace(100,200,n);ua=100+.2*flow
    physics=pd.DataFrame({"timestamp":t,"hx_id":hx,"operating_valid":True,"ua_valid":True,"ua_w_m2_k":ua,"q_cold_value":flow*10,"cold_out_c":100+flow*.02,"lmtd_value":30+flow*.01,"cold_flow_m3_h":flow,"hot_in_c":150+flow*.01,"cold_in_c":40+flow*.01,"sg_15_6c":.82})
    cit=pd.DataFrame({"timestamp":t,"measured_cit_c":200+.3*ua})
    return physics,cit

def test_partial_correlation_controls_common_driver():
    x=np.arange(100.);f=pd.DataFrame({"x":x,"y":2*x+np.sin(x),"c":x})
    assert abs(partial_correlation(f,"x","y",["c"]))<.2

def test_screening_is_exploratory_and_uses_holdout():
    p,c=fixture();relationships,models=screen_relationships(p,c,minimum=60)
    assert (relationships.status=="EXPLORATORY").all()
    assert not relationships.causal_or_cleaning_benefit_interpretation_allowed.any()
    assert models.loc[0,"test_count"]==20

def test_e113a_direct_cit_identity_is_flagged():
    p,c=fixture("E113A");relationships,_=screen_relationships(p,c,minimum=60)
    row=relationships[relationships.x_variable=="cold_out_c"].iloc[0]
    assert row.target_leakage_warning=="DIRECT_CIT_IDENTITY"
