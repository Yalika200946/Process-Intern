import pandas as pd

from pipeline.run_critical_correction_batch import area_f_audit, cpht2_reference_review, validate_branch_15


def test_area_audit_never_calls_area_dependent_u_verified_without_f():
    config = {"heat_exchangers": {"HX": {"status": "READY", "area_m2": 10.0}}}
    diagnostics = {"HX": {"sheets": [{"area_m2": 10.0}]}}
    row = area_f_audit(config, diagnostics).iloc[0]
    assert not row.F_available
    assert row.current_metric_name == "apparent_UA_F1"
    assert row.current_unit == "kW/K"


def test_area_mismatch_is_explicit_and_requires_numerical_change():
    config = {"heat_exchangers": {"HX": {"status": "READY", "area_m2": 10.0}}}
    diagnostics = {"HX": {"sheets": [{"area_m2": 20.0}]}}
    row = area_f_audit(config, diagnostics).iloc[0]
    assert row.numerical_change_required
    assert row.status == "AREA_MISMATCH_REQUIRES_REVIEW"


def test_candidate_reference_blocks_mapping_warning_and_never_confirms_clean():
    physics = pd.DataFrame({"hx_id": ["E105AB"], "operating_valid": [True], "ua_valid": [True], "ua_value": [5.0]})
    candidates = pd.DataFrame([{"hx_id": "E105AB", "candidate_start": "2025-01-01", "candidate_end": "2025-01-30",
                                "valid_record_count": 30, "median_ua_w_m2_k": 100.0, "ua_variability_cv": .01,
                                "crude_flow_variability_cv": .01, "temperature_stability_mean_std_c": 1.0}])
    result = cpht2_reference_review(physics, candidates)
    row = result[result.hx_id.eq("E105AB")].iloc[0]
    assert row.status == "BLOCKED_BY_CONFIGURATION"
    assert not row.clean_condition_confirmed
    assert not row.cleaning_event_confirmed


def test_pilot_propagation_uses_chronological_holdout_and_requires_threshold():
    times = pd.date_range("2025-01-01", periods=50, tz="Asia/Bangkok")
    rows = []
    for i, t in enumerate(times):
        inlet = 50 + i * .1; mid = inlet + 10; outlet = mid + 8
        common = {"timestamp": t, "cold_flow_m3_h": 100 + i * .2, "hot_in_c": 150 + i * .1,
                  "hot_out_c": 110 + i * .1, "sg_15_6c": .85, "operating_valid": True}
        rows.append({**common, "hx_id": "E103AB", "cold_in_c": inlet, "cold_out_c": mid})
        rows.append({**common, "hx_id": "E104", "cold_in_c": mid, "cold_out_c": outlet})
    _, metrics = validate_branch_15(pd.DataFrame(rows))
    assert set(metrics.status) == {"ENGINEERING_THRESHOLD_REQUIRED"}
    assert set(metrics.validation_method) == {"chronological_80_20_holdout_sequential_propagation"}
    assert (metrics.valid_test_cases == 10).all()
