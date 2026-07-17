"""
Shared degradation-curve model library + AIC-based model selection.

Single source of truth for the parametric curve shapes used to describe HX
fouling behavior over a run's days-on-duty. Imported by both the PHM engine
(pipeline/phm_analysis.py, fits the RISING cold-out deviation signal) and the
fouling-rate estimator (notebooks/nb_audit.py, fits the FALLING U_relative
signal) so the two pipelines never diverge on curve-fitting mechanics.

Physical motivation: a fouling exchanger's heat-transfer performance does not
decline as a single straight line for the life of a run — it typically shows a
fast initial decline while the fouling film is forming, then flattens as the
film approaches a mature/asymptotic thickness (Kern-Seaton form). Fitting a
single linear regression across both regimes biases the reported rate. This
module fits several candidate shapes (linear / asymptotic / power) and picks
the best by AIC, so a run that hasn't left the linear regime isn't force-fit
to a 3-parameter curve it doesn't need (AIC's parameter-count penalty already
discourages overfitting short/noisy runs).
"""
import numpy as np
from scipy.optimize import curve_fit


def m_linear(t, a, b):
    return a * t + b


def m_asymp(t, A, tau, c):
    """Rising asymptote: A*(1-exp(-t/tau))+c. For signals that GROW toward a ceiling
    (e.g. cold-out temperature deviation growing as fouling worsens)."""
    return A * (1 - np.exp(-t / np.maximum(tau, 1e-6))) + c


def m_asymp_decay(t, A, tau, c):
    """Falling asymptote: A*exp(-t/tau)+c. For signals that DECAY toward a floor
    (e.g. U_relative falling as the fouling film matures). Mirror image of m_asymp."""
    return A * np.exp(-t / np.maximum(tau, 1e-6)) + c


def m_power(t, a, b, c):
    return a * np.power(np.maximum(t, 1e-6), b) + c


MODELS_RISING = {
    'linear':     (m_linear, 2, lambda t, y: [(y[-1] - y[0]) / max(t[-1] - t[0], 1), y[0]]),
    'asymptotic': (m_asymp,  3, lambda t, y: [max(y.max() - y.min(), 1), max(t.max() / 2, 1), y.min()]),
    'power':      (m_power,  3, lambda t, y: [max((y[-1] - y[0]), 1) / max(t[-1] ** 0.5, 1), 0.7, y.min()]),
}

MODELS_FALLING = {
    'linear':     (m_linear, 2, lambda t, y: [(y[-1] - y[0]) / max(t[-1] - t[0], 1), y[0]]),
    'asymptotic': (m_asymp_decay, 3, lambda t, y: [max(y.max() - y.min(), 1e-3), max(t.max() / 2, 1), y.min()]),
    'power':      (m_power,  3, lambda t, y: [min((y[-1] - y[0]), -1e-3) / max(t[-1] ** 0.5, 1), 0.7, y.max()]),
}


def fit_model(name, t, y, models=MODELS_RISING):
    """Fit one candidate shape; returns dict(name, params, sse, aic) or None on failure."""
    f, k, p0 = models[name]
    try:
        popt, _ = curve_fit(f, t, y, p0=p0(t, y), maxfev=8000)
        pred = f(t, *popt)
        sse = float(np.sum((y - pred) ** 2))
        n = len(t)
        aic = n * np.log(sse / n + 1e-12) + 2 * (k + 1)
        return dict(name=name, params=[float(v) for v in popt], sse=sse, aic=float(aic))
    except Exception:
        return None


def best_fit(t, y, models=MODELS_RISING, min_pts=4):
    """Fit every candidate model in `models`, return the AIC-best (or None if none converge
    or too few points). AIC's 2*(k+1) penalty means a straight run stays 'linear' rather
    than being force-fit to a 3-parameter curve that doesn't reduce SSE enough to justify it."""
    if len(t) < min_pts:
        return None
    fits = [fit_model(name, t, y, models) for name in models]
    fits = [f for f in fits if f]
    return min(fits, key=lambda f: f['aic']) if fits else None


def predict_cross(name, params, y0_t, target, models=MODELS_RISING, tmax=1000, direction='rising'):
    """Days from y0_t until the fitted curve reaches `target`."""
    f = models[name][0]
    ts = np.arange(0, tmax)
    yy = f(y0_t + ts, *params)
    hit = np.where(yy >= target)[0] if direction == 'rising' else np.where(yy <= target)[0]
    return int(hit[0]) if len(hit) else None


def tail_slope(name, params, t_eval, models=MODELS_RISING, h=0.5):
    """Numerical derivative (central difference) of the fitted curve at t_eval — the
    'current rate' at the most recent point of the run, honest for a flattening curve
    where the whole-run average rate over-reads the instantaneous rate."""
    f = models[name][0]
    return float((f(t_eval + h, *params) - f(t_eval - h, *params)) / (2 * h))
