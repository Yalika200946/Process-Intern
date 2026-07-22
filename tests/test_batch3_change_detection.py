import numpy as np

from src.events.change_detection import cusum_recovery_screen, ewma_innovation_screen, robust_step_screen


def test_robust_step_detects_sustained_recovery_not_single_spike():
    sustained = np.r_[np.ones(30) * 0.6, np.ones(30) * 0.8]
    spike = np.ones(60) * 0.6; spike[30] = 0.9
    assert robust_step_screen(sustained, minimum_change=.1).candidate.any()
    assert not robust_step_screen(spike, minimum_change=.1).candidate.any()


def test_cusum_uses_only_past_baseline_and_detects_positive_shift():
    values = np.r_[np.ones(30) * .6, np.ones(10) * .7]
    result = cusum_recovery_screen(values, allowance=.001, threshold=.05)
    assert result.candidate.any()
    assert not result.uses_future_confirmation_window.any()


def test_ewma_innovation_detects_large_recovery_and_preserves_method_metadata():
    values = np.r_[np.linspace(.5, .6, 40), .9, np.linspace(.6, .61, 20)]
    result = ewma_innovation_screen(values, span=15, sigma_threshold=3)
    assert result.loc[40, "candidate"]
    assert (result.method == "EWMA_STATE_INNOVATION").all()


def test_constant_signal_produces_no_false_candidates():
    values = np.ones(80)
    assert not cusum_recovery_screen(values).candidate.any()
    assert not ewma_innovation_screen(values).candidate.any()
