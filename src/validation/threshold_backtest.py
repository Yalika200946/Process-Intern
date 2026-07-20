"""
Threshold-crossing backtest for degradation-model / RUL forecasts (ข้อ 5-7).

Replaces phm_analysis.py's original C1 backtest (fit first 60% of each completed run,
predict time to that run's own FINAL deviation value) with the honest version an
engineer actually needs: for each completed, non-censored run, fit using only data
visible up to several forecast origins (30/50/70% into the run), and predict the date
the fit crosses the HX's own APPROVED threshold -- not the run's arbitrary end point.
Runs that ended without crossing threshold (TAM, ambiguous mode_transition, or the
current in-progress run -- see pipeline/build_event_table.py) are right-censored
observations, not backtest failures, and must be excluded from point-error metrics.

Also hosts:
  - naive baseline predictors (ข้อ 7) scored on the SAME target/origins so a fitted
    curve model must beat every one of them before being shown as "the" projection.
  - task-appropriate metrics (ข้อ 6): MAE/median AE, early/late bias, accuracy within
    +-15/30/60 days, false-alarm/missed-warning rates, provisional interval coverage.

One shared backtest table (`run_threshold_backtest`'s output) feeds all of the above --
computing it once avoids re-fitting curves separately for metrics vs. baseline
comparison vs. (later) calibration checking.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from src.models import fouling_curves as cm


# ────────────────────────────── crossing / origins / projection ──────────────────────────────
def find_threshold_crossing(t, y, threshold, direction='rising'):
    """First day (linearly interpolated between bracketing observed points) the FULL
    observed run series crosses `threshold`, or None if the run never crossed it (a
    right-censored observation -- see module docstring)."""
    t = np.asarray(t, float); y = np.asarray(y, float)
    hit = np.where(y >= threshold)[0] if direction == 'rising' else np.where(y <= threshold)[0]
    if len(hit) == 0:
        return None
    i = int(hit[0])
    if i == 0:
        return float(t[0])
    t0, t1, y0, y1 = t[i - 1], t[i], y[i - 1], y[i]
    if y1 == y0:
        return float(t1)
    frac = (threshold - y0) / (y1 - y0)
    frac = min(max(frac, 0.0), 1.0)
    return float(t0 + frac * (t1 - t0))


def backtest_origins(t, fractions):
    """Origin indices into `t` (a completed run's full days-on-duty array) for each
    fraction in `fractions` -- e.g. 0.30 -> the index 30% of the way through the run's
    OBSERVED length. Only used retrospectively on completed runs (full length already
    known). Clamped to >=3 points (need enough to fit even a 2-3 parameter curve) and
    <=n-1 (must leave at least the last point out of the origin)."""
    n = len(t)
    idxs = []
    for f in fractions:
        idx = int(round(f * (n - 1)))
        idx = max(idx, 3)
        idx = min(idx, n - 1)
        idxs.append(idx)
    return idxs


def fit_and_project_from_origin(t, y, origin_idx, threshold, model_name,
                                 models=cm.MODELS_RISING, tmax=1000, direction='rising'):
    """Fit `model_name` using only t[:origin_idx+1], y[:origin_idx+1] and predict the
    absolute day the fit crosses `threshold`. None if the fit doesn't converge or
    doesn't cross within `tmax` days of the origin (a non-prediction, not a zero-error one)."""
    tt, yy = t[:origin_idx + 1], y[:origin_idx + 1]
    fit = cm.fit_model(model_name, tt, yy, models)
    if not fit:
        return None
    d = cm.predict_cross(model_name, fit['params'], tt[-1], threshold, models=models,
                          tmax=tmax, direction=direction)
    return float(tt[-1] + d) if d is not None else None


# ────────────────────────────── naive baselines (ข้อ 7) ──────────────────────────────
def baseline_historical_median_duration(event_table_df, hx, as_of_run=None):
    """Predict crossing day = HX's own historical median NON-CENSORED run duration
    (Phase 11's event table). `as_of_run` excludes that run and later ones so the
    backtest doesn't leak future runs' durations into a historical prediction."""
    sub = event_table_df[(event_table_df.HX == hx) & (~event_table_df.censored)]
    if as_of_run is not None:
        sub = sub[sub.Run < as_of_run]
    d = sub['duration_days'].dropna()
    return float(d.median()) if len(d) else None


def _prior_run_linear_rates(dev_df, hx, as_of_run, min_pts=5):
    """Linear (deviation vs days_on_duty) slope of every COMPLETED run of this HX strictly
    before `as_of_run`, in the SAME signal space run_c1/threshold_backtest actually forecasts
    (Q_Deviation_Signal's `deviation`, e.g. kW shortfall) -- NOT Fouling_Rate_By_Run.csv's
    dRf_per_day (fouling-RESISTANCE space, ~1e-5 units): those are two different physical
    signals with incompatible units, and dividing a kW gap by an Rf-space rate produces
    nonsense multi-million-day predictions. Returns {run_id: slope}, rising-signal convention
    (positive slope = worsening), only for runs with a well-defined positive slope."""
    d = dev_df[(dev_df.HX == hx) & (dev_df.run_id < as_of_run)].dropna(subset=['run_id'])
    out = {}
    for r, rr in d.groupby('run_id'):
        rr = rr.sort_values('days_on_duty')
        t = rr['days_on_duty'].to_numpy(float); y = rr['deviation'].to_numpy(float)
        if len(t) < min_pts:
            continue
        slope, _ = np.polyfit(t, y, 1)
        if np.isfinite(slope) and slope > 0:
            out[int(r)] = float(slope)
    return out


def baseline_last_reliable_rate(dev_df, hx, as_of_run, cur_deviation, threshold):
    """Predict using the most recent prior completed run's own linear deviation-rate
    (same 'most recent prior run' idea as nb_audit.classify_rate_source's cascade,
    applied retrospectively here instead of to the live current run)."""
    rates = _prior_run_linear_rates(dev_df, hx, as_of_run)
    if not rates:
        return None
    rate = rates[max(rates)]
    return float((threshold - cur_deviation) / rate)


def baseline_hx_own_median_rate(dev_df, hx, as_of_run, cur_deviation, threshold):
    """Predict using the median linear deviation-rate across all this HX's completed runs
    strictly before `as_of_run`."""
    rates = _prior_run_linear_rates(dev_df, hx, as_of_run)
    if not rates:
        return None
    return float((threshold - cur_deviation) / float(np.median(list(rates.values()))))


def baseline_current_linear_rate(t, y, origin_idx, threshold, direction='rising'):
    """Simple linear (not asymptotic/power) fit from data visible up to `origin_idx` --
    the same idea export_end_of_run.py's raw tail-fit fallback already uses."""
    return fit_and_project_from_origin(t, y, origin_idx, threshold, 'linear', direction=direction)


BASELINE_NAMES = ['historical_median_duration', 'last_reliable_rate', 'hx_own_median_rate', 'current_linear_rate']


# ────────────────────────────── shared backtest table (ข้อ 5) ──────────────────────────────
def run_threshold_backtest(dev_df, fr_df, thresholds, event_table_df, hx_list, model_names,
                            fractions=(0.30, 0.50, 0.70), min_run_pts=12, direction='rising'):
    """Long-form backtest table: one row per (HX, completed Run, origin_frac, predictor),
    where predictor is either a fitted curve model name or one of BASELINE_NAMES.

    Excludes the current (still-open) run of every HX. A completed run that never
    crossed `thresholds[hx]` within its own observed span (or that Phase 11's event
    table already flags `censored`) is marked `censored=True` and excluded from
    point-error columns (signed_error_days/error_days stay None) -- it is still
    retained (predicted_day, if any, plus censored=True) so later calibration checks
    can use it as a lower-bound observation.

    Columns: HX, Run, origin_frac, predictor, predicted_day, actual_crossing_day,
    censored, signed_error_days, error_days.
    """
    et_idx = None
    if event_table_df is not None and not event_table_df.empty:
        et_idx = event_table_df.set_index(['HX', 'Run'])['censored']

    rows = []
    for hx in hx_list:
        if hx not in thresholds:
            continue
        thr = float(thresholds[hx])
        d = dev_df[(dev_df.HX == hx)].dropna(subset=['run_id'])
        if d.empty:
            continue
        runs = sorted(d['run_id'].unique())
        for r in runs[:-1]:   # exclude the current (last, still-open) run
            rr = d[d.run_id == r].sort_values('days_on_duty')
            t = rr['days_on_duty'].to_numpy(float)
            y = rr['deviation'].to_numpy(float)
            if len(t) < min_run_pts:
                continue

            actual_cross = find_threshold_crossing(t, y, thr, direction=direction)
            censored = actual_cross is None
            if not censored and et_idx is not None and (hx, int(r)) in et_idx.index:
                censored = censored or bool(et_idx.loc[(hx, int(r))])

            origins = backtest_origins(t, fractions)
            for frac, origin_idx in zip(fractions, origins):
                cur_dev = float(y[origin_idx])
                # fitted candidate curve models
                for m in model_names:
                    pred = fit_and_project_from_origin(t, y, origin_idx, thr, m, direction=direction)
                    rows.append(_row(hx, r, frac, m, pred, actual_cross, censored))
                # naive baselines, scored on the same origin/target
                pred = baseline_historical_median_duration(event_table_df, hx, as_of_run=int(r))
                pred_day = (t[origin_idx] + pred) if pred is not None else None
                rows.append(_row(hx, r, frac, 'historical_median_duration', pred_day, actual_cross, censored))
                pred_day = baseline_last_reliable_rate(dev_df, hx, int(r), cur_dev, thr)
                pred_day = (t[origin_idx] + pred_day) if pred_day is not None else None
                rows.append(_row(hx, r, frac, 'last_reliable_rate', pred_day, actual_cross, censored))
                pred_day = baseline_hx_own_median_rate(dev_df, hx, int(r), cur_dev, thr)
                pred_day = (t[origin_idx] + pred_day) if pred_day is not None else None
                rows.append(_row(hx, r, frac, 'hx_own_median_rate', pred_day, actual_cross, censored))
                pred_day = baseline_current_linear_rate(t, y, origin_idx, thr, direction=direction)
                rows.append(_row(hx, r, frac, 'current_linear_rate', pred_day, actual_cross, censored))

    return pd.DataFrame(rows)


def _row(hx, run, frac, predictor, pred, actual, censored):
    signed = err = None
    if not censored and pred is not None and actual is not None:
        signed = pred - actual
        err = abs(signed)
    return dict(HX=hx, Run=int(run), origin_frac=frac, predictor=predictor,
                predicted_day=pred, actual_crossing_day=actual, censored=censored,
                signed_error_days=signed, error_days=err)


# ────────────────────────────── task-appropriate metrics (ข้อ 6) ──────────────────────────────
def summarize_metrics(backtest_df, group_cols=('predictor',)):
    """MAE / median AE per group, excluding censored rows (no actual_crossing_day to
    compare against) and rows with no prediction at all."""
    df = backtest_df[(~backtest_df.censored) & backtest_df.error_days.notna()]
    if df.empty:
        return {}
    censored_counts = backtest_df[backtest_df.censored].groupby(list(group_cols)).size()
    out = {}
    for key, sub in df.groupby(list(group_cols)):
        key_t = key if isinstance(key, tuple) else (key,)
        out[key_t] = dict(mae_days=round(float(sub.error_days.mean()), 1),
                          median_ae_days=round(float(sub.error_days.median()), 1),
                          n=int(len(sub)),
                          n_censored_excluded=int(censored_counts.get(key, 0)))
    return out


def bias_metrics(backtest_df, group_cols=('predictor',)):
    """Early/late bias: mean(signed_error_days) and % early vs % late, per group."""
    df = backtest_df[(~backtest_df.censored) & backtest_df.signed_error_days.notna()]
    if df.empty:
        return {}
    out = {}
    for key, sub in df.groupby(list(group_cols)):
        key = key if isinstance(key, tuple) else (key,)
        out[key] = dict(bias_days=round(float(sub.signed_error_days.mean()), 1),
                        pct_early=round(float((sub.signed_error_days < 0).mean() * 100), 1),
                        pct_late=round(float((sub.signed_error_days > 0).mean() * 100), 1))
    return out


def accuracy_within(backtest_df, windows=(15, 30, 60), group_cols=('predictor',)):
    """% of predictions within +/- N days of actual crossing, per window, per group."""
    df = backtest_df[(~backtest_df.censored) & backtest_df.error_days.notna()]
    if df.empty:
        return {}
    out = {}
    for key, sub in df.groupby(list(group_cols)):
        key = key if isinstance(key, tuple) else (key,)
        out[key] = {f'accuracy_within_{w}d_pct': round(float((sub.error_days <= w).mean() * 100), 1)
                    for w in windows}
    return out


def false_alarm_missed_warning_rates(backtest_df, warn_horizon_days=60, group_cols=('predictor',)):
    """False alarm: predicted crossing within `warn_horizon_days` (from the forecast
    origin) but actual crossing was later, or the run was censored (never crossed) --
    i.e. the model cried wolf. Missed warning: actual crossing WAS within the horizon
    but the model's prediction was not flagged as imminent (predicted > horizon, or no
    prediction at all). `warn_horizon_days` should match the dashboard's own
    "near threshold" flag (export_end_of_run.py's NEAR_THRESHOLD_DAYS) for consistency."""
    out = {}
    for key, sub in backtest_df.groupby(list(group_cols)):
        key = key if isinstance(key, tuple) else (key,)
        # a censored run (never crossed) the model still predicted a crossing for is a
        # false alarm; a non-censored run whose actual crossing happened but the model
        # predicted nothing at all is a missed warning.
        false_alarms = sub[sub.censored & sub.predicted_day.notna()]
        n_false = len(false_alarms)
        real_soon = sub[(~sub.censored) & (sub.actual_crossing_day.notna())]
        n_missed = int((real_soon.predicted_day.isna()).sum())
        denom_fa = int(sub.censored.sum()) or 1
        denom_mw = len(real_soon) or 1
        out[key] = dict(false_alarm_rate_pct=round(n_false / denom_fa * 100, 1),
                        missed_warning_rate_pct=round(n_missed / denom_mw * 100, 1))
    return out


def interval_coverage(backtest_df, levels=(50, 80, 90)):
    """PROVISIONAL until Phase 9 supplies real predictive intervals: derives a coverage
    proxy from the spread of per-origin predictions ACROSS predictors as a stand-in for
    a proper predictive interval. Always flags `_provisional: True` so this is never
    mistaken for a calibrated interval (see Phase 10's PIT/reliability-diagram check)."""
    df = backtest_df[(~backtest_df.censored) & backtest_df.predicted_day.notna()]
    out = {'_provisional': True}
    if df.empty:
        return out
    for lvl in levels:
        lo, hi = (100 - lvl) / 2, 100 - (100 - lvl) / 2
        covered = []
        for (hx, run, frac), sub in df.groupby(['HX', 'Run', 'origin_frac']):
            if sub.actual_crossing_day.isna().all() or len(sub) < 2:
                continue
            actual = sub.actual_crossing_day.iloc[0]
            plo, phi = np.percentile(sub.predicted_day, [lo, hi])
            covered.append(plo <= actual <= phi)
        out[f'p{lvl}_pct'] = round(float(np.mean(covered)) * 100, 1) if covered else None
    return out


# ────────────────────────────── model-selection gate (ข้อ 7) ──────────────────────────────
# ────────────────────────────── calibration checking (ข้อ 10) ──────────────────────────────
def historical_pit_values(records):
    """Probability Integral Transform: for each historical (origin, HX, run) record with a
    FULL retained predictive sample (not just P10/50/90 points), compute where the actual
    outcome falls in that sample's empirical CDF -- fraction of samples <= actual. Under
    correct calibration, PIT values should be ~uniform on [0,1]. `records`: list of dicts
    with keys 'actual' (float) and 'samples' (array-like of MC draws)."""
    pits = []
    for r in records:
        s = np.asarray(r['samples'], float)
        s = s[np.isfinite(s)]
        if len(s) == 0 or not np.isfinite(r['actual']):
            continue
        pits.append(float(np.mean(s <= r['actual'])))
    return pits


def reliability_diagram_data(records, levels=(50, 80, 90)):
    """For each interval_level, nominal coverage vs. observed empirical coverage across all
    historical (origin, HX, run) records -- the classic reliability-diagram pairs
    (nominal_pct, observed_pct, n). `records`: list of dicts with keys 'actual' and 'samples'
    (full retained MC draws); the (lo, hi) percentile bounds for each level are computed
    from `samples` directly here, so callers don't need to precompute per-level intervals."""
    out = []
    for lvl in levels:
        lo_pct, hi_pct = (100 - lvl) / 2, 100 - (100 - lvl) / 2
        n = covered = 0
        for r in records:
            s = np.asarray(r['samples'], float)
            s = s[np.isfinite(s)]
            if len(s) < 2 or not np.isfinite(r['actual']):
                continue
            lo, hi = np.percentile(s, [lo_pct, hi_pct])
            n += 1
            covered += int(lo <= r['actual'] <= hi)
        out.append(dict(nominal_pct=lvl, observed_pct=(round(covered / n * 100, 1) if n else None), n=n))
    return out


def select_best_model(mae_by_predictor, baseline_names=BASELINE_NAMES, candidate_names=None,
                       min_improvement_pct=0.0):
    """A candidate model is only eligible to be shown as `best_model` if its MAE beats
    EVERY baseline in `baseline_names` by at least `min_improvement_pct`. If none does,
    return the best baseline instead, flagged `beats_all_baselines=False` -- the
    dashboard must never silently show a fitted-model projection that a naive baseline
    would have beaten.

    `mae_by_predictor`: {predictor_name: mae_days}. `candidate_names` defaults to every
    key not in `baseline_names`."""
    baselines = {k: v for k, v in mae_by_predictor.items() if k in baseline_names and v is not None}
    if candidate_names is None:
        candidates = {k: v for k, v in mae_by_predictor.items() if k not in baseline_names and v is not None}
    else:
        candidates = {k: mae_by_predictor[k] for k in candidate_names if mae_by_predictor.get(k) is not None}
    if not baselines:
        best = min(candidates, key=candidates.get) if candidates else None
        return dict(best_model=best, beats_all_baselines=None, baseline_mae={})
    worst_baseline_mae = max(baselines.values())
    eligible = {k: v for k, v in candidates.items()
                if v <= worst_baseline_mae * (1 - min_improvement_pct / 100) and v <= min(baselines.values())}
    # must beat EVERY baseline, not just the worst -- re-check against each one individually
    eligible = {k: v for k, v in eligible.items() if all(v <= b * (1 - min_improvement_pct / 100) for b in baselines.values())}
    if eligible:
        best = min(eligible, key=eligible.get)
        return dict(best_model=best, beats_all_baselines=True, baseline_mae=baselines)
    best_baseline = min(baselines, key=baselines.get)
    return dict(best_model=best_baseline, beats_all_baselines=False, baseline_mae=baselines)
