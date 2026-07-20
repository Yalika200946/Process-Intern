"""
Censored survival analysis for HX run-duration reliability (ข้อ 12).

Replaces phm_analysis.py's original C3 fit (`scipy.stats.weibull_min.fit(durations, floc=0)`
on EVERY run's Duration_days, unconditionally) which treated a run ending in a plant-wide
TAM, an ambiguous mode_transition, or the current still-open run as an equivalent "failure"
event to a real threshold-driven clean. That silently biases the estimated MTBC toward
whatever mix of TAM/ambiguous/censored runs happens to be in the historical data (usually
downward, since TAM/censored runs are cut short for reasons unrelated to the HX's own
condition).

Durations + censoring flags come from pipeline/build_event_table.py's taxonomy (ข้อ 11):
threshold_driven_clean / preventive_clean are OBSERVED events (event_observed=True);
TAM / mode_transition / censored_in_progress are right-censored (event_observed=False).

Thin wrappers over `lifelines` so the rest of the codebase doesn't need to know the
library's API -- callers get back the same shape/scale/MTBC/curve fields C3 already produced,
so the dashboard's existing Weibull R(t) chart needs no changes; `fit_km` additionally
provides a model-free Kaplan-Meier curve as a sanity check on the parametric Weibull fit.
"""
from __future__ import annotations
import numpy as np
from scipy.special import gamma as gammafn
from lifelines import KaplanMeierFitter, WeibullFitter


def fit_km(durations, event_observed):
    """Kaplan-Meier non-parametric survival estimate. Returns (kmf, curve) where curve is
    a list of {t, survival, ci_lower, ci_upper} dicts suitable for direct JSON serialization
    / dashboard overlay on the parametric Weibull R(t) curve."""
    kmf = KaplanMeierFitter()
    kmf.fit(durations, event_observed=event_observed)
    sf = kmf.survival_function_.iloc[:, 0]
    ci = kmf.confidence_interval_
    curve = [dict(t=round(float(t), 1), survival=round(float(s), 4),
                  ci_lower=round(float(ci.iloc[i, 0]), 4), ci_upper=round(float(ci.iloc[i, 1]), 4))
             for i, (t, s) in enumerate(sf.items())]
    return kmf, curve


def fit_weibull_censored(durations, event_observed):
    """lifelines.WeibullFitter equivalent of the old `scipy.stats.weibull_min.fit(..., floc=0)`
    call, but respecting censoring. Same parameterization as scipy's floc=0 fit
    (S(t) = exp(-(t/scale)^shape)), so shape/scale/MTBC stay directly comparable to the old
    (uncensored) numbers -- the difference in the fitted values is attributable to censoring,
    not a parameterization change."""
    wf = WeibullFitter()
    wf.fit(durations, event_observed=event_observed)
    shape, scale = float(wf.rho_), float(wf.lambda_)
    mtbc = scale * gammafn(1 + 1 / shape)
    return wf, shape, scale, mtbc


def per_hx_survival(durations, event_observed, pooled_shape, pooled_scale, min_n=4):
    """Per-HX fit with the SAME low-n fallback structure the old (uncensored) C3 had:
    >=min_n runs get their own censored Weibull fit; fewer get the pooled shape with a
    per-HX scale derived from the mean duration (KNOWN SIMPLIFICATION, unchanged from the
    original code: this mean-duration fallback does not itself account for censoring --
    if an HX's few runs are ALL censored, the resulting scale still underestimates true
    MTBC, since a censored run's true failure time is >= its observed duration, not equal
    to it. Flagged here rather than silently inherited; fixing it properly needs a
    censored-mean estimator, e.g. Kaplan-Meier's restricted mean survival time, which is
    out of scope for this fallback branch); falls back further to fully pooled if there
    are zero usable runs at all. Returns (shape, scale, mtbc, n, confidence) -- confidence
    in {'ok','low','pooled'}, matching the old vocabulary."""
    n = len(durations)
    if n >= min_n:
        try:
            _, shape, scale, mtbc = fit_weibull_censored(durations, event_observed)
            return shape, scale, mtbc, n, 'ok'
        except Exception:
            pass   # fall through to pooled fallback (e.g. all-censored HX, fit can't converge)
    if n >= 1:
        shape = pooled_shape
        mean_dur = float(np.mean(durations))
        scale = mean_dur / gammafn(1 + 1 / shape) if mean_dur > 0 else pooled_scale
        mtbc = scale * gammafn(1 + 1 / shape)
        return shape, scale, mtbc, n, 'low'
    mtbc = pooled_scale * gammafn(1 + 1 / pooled_shape)
    return pooled_shape, pooled_scale, mtbc, n, 'pooled'
