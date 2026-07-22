from pipeline.build_fast_track_report import ALLOWED,blockers,stage_gate

def test_every_stage_has_exact_allowed_status():
    stages=stage_gate();assert stages.status.notna().all();assert set(stages.status)<=ALLOWED

def test_unsupported_conclusions_are_explicitly_blocked_or_unavailable():
    out=blockers();assert set(out.status)<={"BLOCKED","UNAVAILABLE"};assert "FULL_NETWORK_MODEL" in set(out.output);assert "FINAL_CLEANING_RECOMMENDATION" in set(out.output)
