"""
Bootstrap / partial-pooling uncertainty for the Monte-Carlo RUL estimate (ข้อ 8).

Replaces phm_analysis.py's original C2 sampling (`rng.normal(rate, rel_sd*rate, MC_ITERS)`)
-- a PARAMETRIC normal assumption on the rate, with no cross-HX information sharing when a
given HX has very few historical runs (the old fallback was a single hardcoded constant,
`RATE_REL_SD_FALLBACK`, not informed by similar HX at all).

Unit-space note (the same pitfall found and fixed in threshold_backtest.py's baselines):
run_c2's rate is in Q-deviation kW/day space (Time_To_Clean_Prediction.csv), NOT
Fouling_Rate_By_Run.csv's Rf-space dRf_per_day -- pooling absolute historical rates across
HX with very different duty scales would also be physically wrong (E113A's kW/day rate and
E102's kW/day rate aren't comparable in absolute terms even if both are "fouling fast" for
their own scale). This module instead bootstraps the historical run-to-run RATE RATIO
(rate / that HX's own median historical rate) -- a unit-free multiplicative noise factor
that IS meaningfully comparable across HX, applied to the live current-run point rate. This
also makes partial pooling from topologically-similar HX sound: pooling "how variable is
the rate run-to-run, relatively speaking" across HX in the same hot-stream/train position is
a defensible physical prior; pooling raw kW/day rates across different-duty HX would not be.
"""
from __future__ import annotations
import numpy as np


def historical_run_rates(dev_df, hx, as_of_run, min_pts=5):
    """Linear (deviation vs days_on_duty) slope of every completed run of this HX strictly
    before `as_of_run` -- same helper threshold_backtest.py's baselines use, kept here as a
    thin re-export so callers of this module don't need to import validation code."""
    from src.validation.threshold_backtest import _prior_run_linear_rates
    return list(_prior_run_linear_rates(dev_df, hx, as_of_run, min_pts=min_pts).values())


def bootstrap_rate_ratios(rates):
    """Historical per-run rates -> unit-free ratios (rate / median(rates)). None if fewer
    than 2 usable (finite, positive) historical rates -- not enough to characterize spread."""
    rates = np.asarray(rates, float)
    rates = rates[np.isfinite(rates) & (rates > 0)]
    if len(rates) < 2:
        return None
    med = float(np.median(rates))
    return rates / med if med > 0 else None


def topology_similar_hx(hx, topo_json, k=3):
    """k topologically 'nearest' HX to `hx` for partial pooling, using
    dashboard/data/pfd_topology.json's existing per-node hot_stream/group/parallel_with
    fields (reuse the topology data already built for the P&ID view, not a new similarity
    metric): same hot stream (+2), same CPHT-1/CPHT-2 group (+1), direct parallel-shell
    pairing (+3, the strongest physical similarity -- parallel shells see the same crude
    at the same train position). Ties broken by node order in the topology file."""
    nodes = (topo_json or {}).get('nodes', {})
    me = nodes.get(hx)
    if me is None:
        return []
    scored = []
    for other, node in nodes.items():
        if other == hx:
            continue
        score = 0
        if node.get('hot_stream') and node.get('hot_stream') == me.get('hot_stream'):
            score += 2
        if node.get('group') and node.get('group') == me.get('group'):
            score += 1
        if node.get('parallel_with') == hx or me.get('parallel_with') == other:
            score += 3
        if score > 0:
            scored.append((score, other))
    scored.sort(key=lambda x: -x[0])
    return [h for _, h in scored[:k]]


def partial_pooled_rate_samples(rate_point, rates_by_hx, hx, topo_json, n_iter=10000,
                                 min_n_for_own_data=4, rng=None):
    """Bootstrap-resample rate ratios for `hx` -- its OWN historical ratios if it has
    >= min_n_for_own_data usable historical runs, otherwise pooled with topologically
    similar HX's ratios (own ratios included if any exist, weighted equally with pooled
    ones -- a simple, auditable scheme, not a hierarchical Bayesian model). Multiplies the
    resampled ratios by `rate_point` (the live current-run rate) to get `n_iter` rate
    samples in the SAME units as `rate_point`.

    Returns (samples, meta) where samples is None if there's no usable historical rate data
    at all (own or pooled) -- caller should fall back to a documented flat assumption in
    that case, not silently produce an empty/zero-width distribution.
    """
    rng = rng or np.random.default_rng()
    own_ratios = bootstrap_rate_ratios(rates_by_hx.get(hx, []))
    own_n = 0 if own_ratios is None else len(own_ratios)
    pooled_from = []

    if own_n >= min_n_for_own_data:
        ratio_pool = own_ratios
    else:
        parts = [own_ratios] if own_ratios is not None else []
        for h2 in topology_similar_hx(hx, topo_json, k=3):
            r2 = bootstrap_rate_ratios(rates_by_hx.get(h2, []))
            if r2 is not None:
                parts.append(r2)
                pooled_from.append(h2)
        ratio_pool = np.concatenate(parts) if parts else None

    meta = dict(n_own_reliable_runs=own_n, pooled_from_hx=pooled_from)
    if ratio_pool is None or len(ratio_pool) == 0:
        return None, meta
    draws = rng.choice(ratio_pool, size=n_iter, replace=True)
    return rate_point * draws, meta


# ────────────────────────────── multi-source composition (ข้อ 9) ──────────────────────────────
def draw_current_signal_noise(dev_df, hx, cur_run, n_iter, rng, min_pts=5):
    """Bootstrap residuals from the CURRENT run's own linear (deviation vs days_on_duty) fit
    -- noise/measurement uncertainty in TODAY's signal itself, distinct from (3) rate-fit
    uncertainty. None if the current run doesn't have enough points to fit."""
    d = dev_df[(dev_df.HX == hx) & (dev_df.run_id == cur_run)].dropna(subset=['deviation', 'days_on_duty'])
    if len(d) < min_pts:
        return None
    t = d['days_on_duty'].to_numpy(float); y = d['deviation'].to_numpy(float)
    b, a = np.polyfit(t, y, 1)
    resid = y - (a + b * t)
    if len(resid) < 2 or np.allclose(resid, 0):
        return None
    return rng.choice(resid, size=n_iter, replace=True)


def compose_uncertainty_sources(rate_point, cur_deviation_point, threshold_point, rates_by_hx, hx,
                                 topo_json, dev_df, cur_run, n_iter=10000, rng=None,
                                 min_n_for_own_data=4, threshold_uncertainty_frac=0.02,
                                 operating_state_fallback_sd=0.15):
    """Joint Monte Carlo combining the uncertainty sources this project can currently
    characterize, honestly labeled by how each was obtained (not all 6 requirements-doc
    sources are implemented -- see `sources` return value for exactly which):

      1. rate_fit          -- (ข้อ 8) bootstrap/partial-pooled historical rate ratios.
      2. signal_noise      -- bootstrap residuals from the current run's own fit.
      3. threshold         -- ASSUMED +-`threshold_uncertainty_frac` band (no data yet
                              characterizes real threshold uncertainty; REQUIRES_ENGINEERING_CONFIRMATION).
      4. operating_state   -- ASSUMED flat multiplicative fallback SD, since C4's driver
                              model is gated off (ข้อ 3) and has no data-driven estimate to
                              draw from today.
      5. baseline_choice   -- NOT APPLICABLE here: C2 forecasts from a single point rate (no
                              multi-model race the way C1 has); marked 'not_applicable'.
      6. crude_scenario    -- NOT IMPLEMENTED in this pass (would need historical crude-window
                              resampling); marked 'not_implemented', not faked.

    Returns (rul_samples, sources) where `sources` maps each name to True/False (data-driven,
    used/not-used) or a short string tag for assumed/fallback/not-implemented/not-applicable
    sources, so the dashboard can show exactly which parts of the interval are measured vs
    engineering judgment (CLAUDE.md's MEASURED/CALCULATED/INFERRED/ASSUMED discipline)."""
    rng = rng or np.random.default_rng()
    sources = {}

    rate_samples, pool_meta = partial_pooled_rate_samples(
        rate_point, rates_by_hx, hx, topo_json, n_iter=n_iter,
        min_n_for_own_data=min_n_for_own_data, rng=rng)
    if rate_samples is None:
        rate_samples = np.full(n_iter, rate_point)
        sources['rate_fit'] = False
    else:
        sources['rate_fit'] = True

    resid = draw_current_signal_noise(dev_df, hx, cur_run, n_iter, rng)
    if resid is not None:
        cur_dev_samples = cur_deviation_point + resid
        sources['signal_noise'] = True
    else:
        cur_dev_samples = np.full(n_iter, cur_deviation_point)
        sources['signal_noise'] = False

    thr_samples = rng.normal(threshold_point, max(threshold_uncertainty_frac * abs(threshold_point), 1e-6), n_iter)
    sources['threshold'] = 'assumed_band'

    os_mult = rng.normal(1.0, operating_state_fallback_sd, n_iter)
    rate_samples = rate_samples * os_mult
    sources['operating_state'] = 'fallback_flat_band'

    sources['baseline_choice'] = 'not_applicable_single_rate_model'
    sources['crude_scenario'] = 'not_implemented'

    gap_samples = thr_samples - cur_dev_samples
    floor = abs(rate_point) * 0.05 if rate_point else 1e-6
    rate_samples = np.clip(rate_samples, floor, None)
    rul_samples = gap_samples / rate_samples
    # a draw where threshold/signal noise pushes the simulated current deviation AT OR PAST
    # the simulated threshold means "already needs cleaning in that scenario" (RUL=0), not a
    # negative day count -- clip rather than let a physically meaningless negative number
    # leak into P10 (this is the same convention run_c2's `past_threshold` branch already
    # uses for the point estimate).
    rul_samples = np.clip(rul_samples, 0, None)
    return rul_samples, sources, pool_meta
