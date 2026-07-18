"""
Regression tests for nb_audit.robust_fouling_rate's physical-constraint checks and
label_fouling_phase -- previously the "reliable run never has slope>=0" invariant was only
an assert inside pipeline/compute_fouling_rate.py, which only fires when someone runs the
full pipeline against the real ~500K-row dataset. These run fast against small synthetic
runs so the invariant is checked on every code change, not just a full pipeline run.

docs/requirements/03_Business_Problem_and_Requirements.md flags zero automated tests anywhere in the
repo as a gap -- this is a starting point (highest-risk, already-fragile logic), not full
coverage of the pipeline.
"""
import numpy as np

from src.validation import nb_audit as A


def _synthetic_run(n=60, true_slope=-0.002, noise=0.01, start=1.0, seed=0):
    """A clean, monotonically-fouling synthetic run: U_relative starts near 1.0 and decays
    linearly (plus noise) over `n` in-service days -- enough points/span to clear
    robust_fouling_rate's data-sufficiency gates (min_span_days=30, min_pts=20)."""
    rng = np.random.default_rng(seed)
    days = np.arange(n, dtype=float)
    u = start + true_slope * days + rng.normal(0, noise, n)
    state = np.array(["NORMAL"] * n)
    return days, u, state


class TestRobustFoulingRatePhysicalInvariant:
    def test_reliable_run_never_has_nonnegative_slope(self):
        """The core physical invariant compute_fouling_rate.py asserts on the real dataset
        (fouling can't reverse itself -- U_relative can't trend upward while marked
        `reliable`)."""
        days, u, state = _synthetic_run()
        res = A.robust_fouling_rate(days, u, state=state)
        if res["reliable"]:
            assert res["dUrel_per_day"] < 0

    def test_flat_run_is_not_reliable(self):
        """A run with no real trend (pure noise around a constant) must not be marked
        reliable -- reliability requires the CI upper bound to be significantly negative."""
        days = np.arange(60, dtype=float)
        rng = np.random.default_rng(1)
        u = 0.9 + rng.normal(0, 0.02, 60)  # flat, no slope
        state = np.array(["NORMAL"] * 60)
        res = A.robust_fouling_rate(days, u, state=state)
        assert not res["reliable"]

    def test_insufficient_span_is_flagged_not_silently_accepted(self):
        """A run shorter than min_span_days must be flagged, not fitted anyway."""
        days = np.arange(10, dtype=float)  # well under min_span_days=30
        u = 1.0 - 0.01 * days
        state = np.array(["NORMAL"] * 10)
        res = A.robust_fouling_rate(days, u, state=state)
        assert not res["reliable"]
        assert res["rate_flag"] == "insufficient_span"

    def test_substituted_dominated_run_is_excluded(self):
        """A run where the HX spends most of its time NOT actually in service (e.g.
        SUBSTITUTED) must not produce a rate at all -- the trend wouldn't reflect this
        HX's own fouling."""
        days, u, _ = _synthetic_run()
        state = np.array(["SUBSTITUTED"] * len(days))  # never actually in service
        res = A.robust_fouling_rate(days, u, state=state)
        assert not res["reliable"]
        assert res["rate_flag"] == "substituted_dominated"


class TestLabelFoulingPhase:
    def test_boundary_matches_initiation_lag_days(self):
        """label_fouling_phase must split at EXACTLY the boundary robust_fouling_rate uses
        internally (INITIATION_LAG_DAYS) -- the whole point of sharing the module constant
        instead of a second, driftable copy of the literal 15."""
        days = np.array([0, 1, A.INITIATION_LAG_DAYS - 1, A.INITIATION_LAG_DAYS,
                         A.INITIATION_LAG_DAYS + 1, 100], dtype=float)
        labels = A.label_fouling_phase(days)
        assert list(labels[:3]) == ["INITIATION"] * 3
        assert list(labels[3:]) == ["AFTER_INITIATION"] * 3

    def test_nan_days_get_no_label(self):
        days = np.array([np.nan, 5.0, np.nan])
        labels = A.label_fouling_phase(days)
        assert labels[0] is None and labels[2] is None
        assert labels[1] == "INITIATION"
