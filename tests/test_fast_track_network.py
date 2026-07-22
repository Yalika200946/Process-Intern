from pipeline.assess_fast_track_network import infer_confirmed_tag_edges,readiness

def fixture():
    return {"aliases":{"T1":"t1.pv"},"heat_exchangers":{"A":{"status":"READY","cold_in":"t0","cold_out":"T1"},"B":{"status":"READY","cold_in":"t1.pv","cold_out":"t2"},"C":{"status":"BLOCKED","blocked_reason":"CONFLICT"}}}

def test_only_identical_temperature_tags_create_validated_edge():
    edges=infer_confirmed_tag_edges(fixture())
    assert len(edges)==1 and edges.iloc[0].upstream_hx=="A" and edges.iloc[0].downstream_hx=="B"
    assert edges.iloc[0].edge_status=="VALIDATED_TAG_CONTINUITY"

def test_network_counterfactual_stays_blocked_without_split_mix_balance():
    cfg=fixture();out=readiness(cfg,infer_confirmed_tag_edges(cfg))
    assert (out.single_hx_counterfactual_status=="BLOCKED").all()
    assert out.loc[out.hx_id=="C","network_readiness_status"].iloc[0]=="BLOCKED"
