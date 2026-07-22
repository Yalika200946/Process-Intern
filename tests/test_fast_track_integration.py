from pipeline.build_fast_track_report import ALLOWED,blockers,plot_coverage,stage_gate

def test_every_stage_has_exact_allowed_status():
    stages=stage_gate();assert stages.status.notna().all();assert set(stages.status)<=ALLOWED

def test_unsupported_conclusions_are_explicitly_blocked_or_unavailable():
    out=blockers();assert set(out.status)<={"BLOCKED","UNAVAILABLE"};assert "FULL_NETWORK_MODEL" in set(out.output);assert "FINAL_CLEANING_RECOMMENDATION" in set(out.output)

def test_plot_coverage_uses_required_generation_contract():
    out=plot_coverage();required={"output_name","stage","required_inputs","eligible_scope","generated_scope","file_path","valid_record_count","generated_status","data_status","reason_if_missing","blocker","next_action"};assert required<=set(out.columns);assert set(out.generated_status)<={"GENERATED","PARTIALLY_GENERATED","NOT_GENERATED","BLOCKED","UNAVAILABLE","FAILED"}
