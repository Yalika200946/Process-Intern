"""
Regression tests for nb_audit.robust_fouling_rate's physical-constraint checks and
label_fouling_phase -- previously the "reliable run never has dRf/dt<=0" invariant was only
an assert inside pipeline/compute_fouling_rate.py, which only fires when someone runs the
full pipeline against the real ~500K-row dataset. These run fast against small synthetic
runs so the invariant is checked on every code change, not just a full pipeline run.

docs/requirements/03_Business_Problem_and_Requirements.md flags zero automated tests anywhere in the
repo as a gap -- this is a starting point (highest-risk, already-fragile logic), not full
coverage of the pipeline.

Rf is now the PRIMARY fitted metric (changed 2026-07-19, to match the mechanistic fouling
literature -- see nb_audit.robust_fouling_rate's docstring), so every synthetic run below
carries a `rf` array alongside `u`, built as the physical inverse Rf = (1/U_relative - 1)
(U_clean=1 for these unitless synthetic tests) so the two stay mutually consistent.
"""
import numpy as np

from src.validation import nb_audit as A


def _synthetic_run(n=60, true_slope=-0.002, noise=0.01, start=1.0, seed=0):
    """A clean, monotonically-fouling synthetic run: U_relative starts near 1.0 and decays
    linearly (plus noise) over `n` in-service days -- enough points/span to clear
    robust_fouling_rate's data-sufficiency gates (min_span_days=30, min_pts=20). `rf` is the
    physically consistent fouling resistance (U_clean=1), which rises as U_relative falls."""
    rng = np.random.default_rng(seed)
    days = np.arange(n, dtype=float)
    u = start + true_slope * days + rng.normal(0, noise, n)
    rf = 1.0 / np.clip(u, 1e-3, None) - 1.0
    state = np.array(["NORMAL"] * n)
    return days, u, rf, state


class TestRobustFoulingRatePhysicalInvariant:
    def test_reliable_run_never_has_nonpositive_rf_slope(self):
        """The core physical invariant compute_fouling_rate.py asserts on the real dataset
        (fouling can't reverse itself -- Rf can't trend downward while marked `reliable`)."""
        days, u, rf, state = _synthetic_run()
        res = A.robust_fouling_rate(days, u, rf_run=rf, state=state)
        if res["reliable"]:
            assert res["dRf_per_day"] > 0

    def test_flat_run_is_not_reliable(self):
        """A run with no real trend (pure noise around a constant) must not be marked
        reliable -- reliability requires the CI lower bound to be significantly positive."""
        days = np.arange(60, dtype=float)
        rng = np.random.default_rng(1)
        u = 0.9 + rng.normal(0, 0.02, 60)  # flat, no slope
        rf = 1.0 / np.clip(u, 1e-3, None) - 1.0
        state = np.array(["NORMAL"] * 60)
        res = A.robust_fouling_rate(days, u, rf_run=rf, state=state)
        assert not res["reliable"]

    def test_insufficient_span_is_flagged_not_silently_accepted(self):
        """A run shorter than min_span_days must be flagged, not fitted anyway."""
        days = np.arange(10, dtype=float)  # well under min_span_days=30
        u = 1.0 - 0.01 * days
        rf = 1.0 / np.clip(u, 1e-3, None) - 1.0
        state = np.array(["NORMAL"] * 10)
        res = A.robust_fouling_rate(days, u, rf_run=rf, state=state)
        assert not res["reliable"]
        assert res["rate_flag"] == "insufficient_span"

    def test_substituted_dominated_run_is_excluded(self):
        """A run where the HX spends most of its time NOT actually in service (e.g.
        SUBSTITUTED) must not produce a rate at all -- the trend wouldn't reflect this
        HX's own fouling."""
        days, u, rf, _ = _synthetic_run()
        state = np.array(["SUBSTITUTED"] * len(days))  # never actually in service
        res = A.robust_fouling_rate(days, u, rf_run=rf, state=state)
        assert not res["reliable"]
        assert res["rate_flag"] == "substituted_dominated"

    def test_missing_rf_data_is_flagged(self):
        """Rf is now the primary fitted quantity -- omitting it entirely must not silently
        fall back to a U_relative-only reliable result."""
        days, u, _, state = _synthetic_run()
        res = A.robust_fouling_rate(days, u, state=state)
        assert not res["reliable"]
        assert res["rate_flag"] == "no_rf_data"


def _synthetic_two_phase_run(seed=2, jump=0.05):
    """Two fouling phases (60 days each) separated by a mid-run U_relative recovery jump --
    used to exercise `intra_run_split_points`/`segment_fouling_rates`'s multi-segment path.
    `jump` is deliberately small (realistic U_relative scale) since the 7-day CENTERED
    rolling-mean smoothing dilutes any single-day step by roughly 1/7 -- callers that want
    the jump to actually register as a cut should pass a correspondingly small
    `intra_recovery` threshold rather than an unrealistically large jump."""
    rng = np.random.default_rng(seed)
    days1 = np.arange(60, dtype=float)
    u1 = 1.0 - 0.0025 * days1 + rng.normal(0, 0.003, 60)
    days2 = np.arange(60, 120, dtype=float)
    u2 = (1.0 + jump) - 0.0025 * (days2 - 60) + rng.normal(0, 0.003, 60)
    days = np.concatenate([days1, days2])
    u = np.concatenate([u1, u2])
    rf = 1.0 / np.clip(u, 1e-3, None) - 1.0
    state = np.array(["NORMAL"] * len(days))
    return days, u, rf, state


class TestSegmentFoulingRates:
    def test_intra_run_split_points_detects_a_sustained_jump(self):
        """A clean, large sustained step in U_relative must register as a cut near the step
        (the centered 7-day rolling mean spreads a step over ~7 days, so the exact cut index
        lands a few days into the transition, not necessarily on day 0 of it)."""
        days = np.arange(40, dtype=float)
        u = np.where(days < 20, 0.5, 1.7)
        cuts = A.intra_run_split_points(days, u, intra_recovery=0.15)
        assert len(cuts) >= 1
        assert 15 <= cuts[-1] <= 25

    def test_no_cut_returns_single_segment_matching_robust_fouling_rate(self):
        """The common case (confirmed empirically: 0/97 real runs in the production dataset
        have any intra-run split) -- segment_fouling_rates must return exactly one segment,
        and it must be numerically identical to robust_fouling_rate's own output, since both
        share the same prep pipeline and `_fit_segment` fitting code."""
        days, u, rf, state = _synthetic_run()
        segs = A.segment_fouling_rates(days, u, rf, state=state)
        auth = A.robust_fouling_rate(days, u, rf_run=rf, state=state)
        assert len(segs) == 1
        for key in ("dRf_per_day", "reliable", "rate_flag", "model_selected", "R2_model"):
            assert segs[-1][key] == auth[key]

    def test_last_segment_matches_authoritative_after_a_real_split(self):
        """When a split IS found, segment_fouling_rates must return >1 segments, and its LAST
        segment must still be numerically identical to what robust_fouling_rate computes for
        the same full run (same intra_recovery threshold) -- proving the refactor didn't
        change robust_fouling_rate's own scalar output even when segmentation kicks in."""
        days, u, rf, state = _synthetic_two_phase_run()
        segs = A.segment_fouling_rates(days, u, rf, state=state, intra_recovery=0.02)
        auth = A.robust_fouling_rate(days, u, rf_run=rf, state=state, intra_recovery=0.02)
        assert len(segs) > 1
        for key in ("dRf_per_day", "reliable", "rate_flag", "model_selected", "R2_model"):
            assert segs[-1][key] == auth[key]


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
