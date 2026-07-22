import numpy as np
import pandas as pd

from pipeline.build_batch4_model_benchmarks import reference_baselines, selection_status


def test_selection_requires_candidate_to_beat_baseline():
    assert selection_status(1.0, 2.0)[0] == "SELECTED_PROVISIONAL"
    assert selection_status(2.0, 1.0) == ("REJECTED", "DID_NOT_BEAT_SIMPLE_BASELINE")


def test_leakage_rejects_even_accurate_candidate():
    status, reason = selection_status(.1, 10, leakage="DIRECT_TARGET_IDENTITY")
    assert status == "REJECTED" and "TARGET_LEAKAGE" in reason


def test_physical_gate_can_limit_winner_to_benchmark_only():
    assert selection_status(1, 2, physics_allowed=False)[0] == "BENCHMARK_ONLY"


def test_reference_baseline_uses_chronological_last_twenty_percent():
    values = np.r_[np.ones(80), np.ones(20) * 2]
    frame = pd.DataFrame({"hx_id":"HX", "timestamp":pd.date_range("2026-01-01", periods=100),
                          "operating_valid":True, "ua_valid":True, "ua_w_m2_k":values})
    result = reference_baselines(frame).iloc[0]
    assert result.train_records == 80 and result.test_records == 20
    assert result.persistence_rmse == 1.0
