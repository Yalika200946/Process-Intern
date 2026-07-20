"""
Shared data-science audit toolkit for the CPHT notebooks (0-6).

Single source of truth for the *systematic* parts of every notebook — data-quality
reporting, honest cross-validation, physical-plausibility checks, and a consistent
"Assumptions & Limitations" header — so each notebook reads like a proper, reproducible
data-engineering analysis instead of ad-hoc cells. Import from here (same pattern as
cpht_config.py) rather than re-writing these blocks per notebook.

Usage in a notebook:
    import nb_audit as A
    A.assumptions_block(objective=..., inputs=[...], outputs=[...],
                        assumptions=[...], limitations=[...])   # -> Markdown at top
    A.data_quality_report(df, name='Process_information_cleaned')
    A.leave_run_out_cv(X, y, groups=run_id, model=Ridge())     # honest CV
    A.plausibility_checks(df, [('dT_cold>0', df['cold_out']-df['cold_in'] > 0), ...])
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from src.models import fouling_curves as cm


# ────────────────────────────── methodology header ──────────────────────────────
def assumptions_block(objective, inputs, outputs, assumptions, limitations, method=None):
    """Return an IPython Markdown object documenting the analysis contract.
    Put this as the FIRST executed cell so a reviewer sees scope + caveats up front."""
    def _ul(items):
        return '\n'.join(f'- {i}' for i in items)
    md = [f"### 🎯 Objective\n{objective}\n",
          f"### 📥 Inputs\n{_ul(inputs)}\n",
          f"### 📤 Outputs\n{_ul(outputs)}\n"]
    if method:
        md.append(f"### 🧪 Method\n{_ul(method)}\n")
    md.append(f"### ⚖️ Assumptions\n{_ul(assumptions)}\n")
    md.append(f"### ⚠️ Limitations\n{_ul(limitations)}")
    text = '\n'.join(md)
    try:
        from IPython.display import Markdown
        return Markdown(text)
    except Exception:
        print(text)
        return text


# ────────────────────────────── data-quality report ──────────────────────────────
def data_quality_report(df, name='', time_col=None, expected_freq='D', show=True):
    """Per-column + dataset-level quality summary. Returns the per-column DataFrame.

    Reports missing %, range, #unique, and dataset-level duplicate rows + time-gaps —
    the standard 'is this data fit to model?' gate every notebook should pass."""
    rep = pd.DataFrame({
        'dtype': df.dtypes.astype(str),
        'missing_%': (df.isna().mean() * 100).round(2),
        'n_unique': df.nunique(),
    })
    num = df.select_dtypes('number')
    if len(num.columns):
        desc = num.describe().T[['min', 'mean', 'max']].round(3)
        rep = rep.join(desc)
    # dataset-level checks
    idx = df.index if isinstance(df.index, pd.DatetimeIndex) else (
        pd.to_datetime(df[time_col]) if time_col and time_col in df.columns else None)
    dupes = int(df.duplicated().sum())
    gaps = None
    if idx is not None and len(idx) > 2:
        d = pd.Series(idx).sort_values()
        step = pd.Timedelta(1, expected_freq)
        gaps = int(((d.diff().dropna()) > step).sum())
    if show:
        print(f'── Data-quality report{": "+name if name else ""} ──')
        print(f'   rows={len(df)}  cols={df.shape[1]}  duplicate_rows={dupes}'
              + (f'  time_gaps>{expected_freq}={gaps}' if gaps is not None else ''))
        worst = rep['missing_%'].sort_values(ascending=False).head(5)
        if worst.iloc[0] > 0:
            print('   highest missing %:', {k: round(v, 1) for k, v in worst.items() if v > 0})
    return rep


# ────────────────────────────── honest cross-validation ──────────────────────────────
def leave_run_out_cv(X, y, groups, model, n_splits=None, scale=True):
    """GroupKFold CV holding out WHOLE runs (groups=run_id) — the honest test for a
    forecaster: never train and test on the same fouling run. Returns per-fold R²/MAE
    and mean±SD. Use instead of a within-run temporal split (which leaks run-level offset)."""
    from sklearn.model_selection import GroupKFold
    from sklearn.metrics import r2_score, mean_absolute_error
    from sklearn.preprocessing import StandardScaler
    from sklearn.base import clone
    X = np.asarray(X, float); y = np.asarray(y, float); groups = np.asarray(groups)
    ng = len(np.unique(groups))
    k = n_splits or min(5, ng)
    if ng < 2 or k < 2:
        return dict(error=f'need >=2 groups, got {ng}')
    gkf = GroupKFold(n_splits=k)
    r2s, maes = [], []
    for tr, te in gkf.split(X, y, groups):
        m = clone(model)
        Xtr, Xte = X[tr], X[te]
        if scale:
            sc = StandardScaler().fit(Xtr); Xtr, Xte = sc.transform(Xtr), sc.transform(Xte)
        m.fit(Xtr, y[tr]); p = m.predict(Xte)
        r2s.append(r2_score(y[te], p)); maes.append(mean_absolute_error(y[te], p))
    return dict(n_groups=int(ng), k=int(k),
                r2_mean=round(float(np.mean(r2s)), 3), r2_sd=round(float(np.std(r2s)), 3),
                mae_mean=round(float(np.mean(maes)), 3), mae_sd=round(float(np.std(maes)), 3),
                r2_folds=[round(v, 3) for v in r2s])


def naive_rate_baseline_cv(t, y, groups):
    """Baseline for degradation forecasting: predict y with a per-run constant-rate
    line fit on that run only (the 'no-model' engineering default). Reported so ML
    models must BEAT it to justify their complexity (same discipline as persistence for CIT)."""
    from sklearn.metrics import r2_score
    t = np.asarray(t, float); y = np.asarray(y, float); groups = np.asarray(groups)
    preds, actual = [], []
    for g in np.unique(groups):
        m = groups == g
        if m.sum() < 3:
            continue
        b, a = np.polyfit(t[m], y[m], 1)
        preds.extend(a + b * t[m]); actual.extend(y[m])
    if not preds:
        return dict(error='insufficient data')
    return dict(r2=round(float(r2_score(actual, preds)), 3), note='per-run linear fit (in-sample floor)')


# ────────────────────────────── physical plausibility ──────────────────────────────
def plausibility_checks(checks, show=True):
    """checks = list of (name, boolean_mask_that_should_be_TRUE). Reports violation counts.
    Encodes engineering invariants (Q>0, cold_out>cold_in, ΔT_hot>0, ...) as gates."""
    rows = []
    for name, ok_mask in checks:
        ok = np.asarray(ok_mask)
        n = ok.size; viol = int((~ok).sum())
        rows.append(dict(check=name, n=n, violations=viol, viol_pct=round(viol / max(n, 1) * 100, 2)))
    rep = pd.DataFrame(rows)
    if show:
        bad = rep[rep.violations > 0]
        print('── Plausibility checks ──')
        if len(bad):
            for _, r in bad.iterrows():
                print(f"   ✗ {r['check']}: {r['violations']}/{r['n']} ({r['viol_pct']}%) violate")
        else:
            print('   ✓ all checks passed')
    return rep


INSERVICE_STATES = ('NORMAL', 'SUBSTITUTE_ACTIVE', 'PARALLEL')  # HX actively transferring heat

# Days-on-duty below this are excluded from the fouling-rate regression in
# robust_fouling_rate below (fast initial film-formation transient, not yet the steady
# after-initiation trend a rate/ranking should be computed from) -- named here as a module
# constant, not just a default-argument literal, so label_fouling_phase() below can use the
# EXACT SAME boundary rather than a second, driftable copy of "15".
INITIATION_LAG_DAYS = 15


def label_fouling_phase(days_on_duty):
    """Per-point INITIATION / AFTER_INITIATION label using the same boundary
    (INITIATION_LAG_DAYS) robust_fouling_rate already uses to exclude early-run points from
    its regression -- that exclusion happens silently inside the fit today; this makes it an
    explicit, visible label instead (docs/03's diagram-derived Phase Separation requirement:
    "Initiation Phase (post-clean/induction)" / "After-initiation Phase (steady-operation)").

    This does NOT change or re-derive the boundary itself, and does not touch
    robust_fouling_rate's fitting logic (AIC race between linear/asymptotic Kern-Seaton
    curves, tail-slope rate, intra-run recovery split -- already a more sophisticated
    phase-aware model than a fixed two-phase label would be on its own). It only exposes,
    as a column other consumers can read/plot, the same cutoff the rate fit already applies.

    NaN days_on_duty (HX not on duty that day) map to None, not a phase label.
    Returns a numpy array of dtype=object with values 'INITIATION'/'AFTER_INITIATION'/None."""
    d = np.asarray(days_on_duty, float)
    label = np.full(d.shape, None, dtype=object)
    valid = np.isfinite(d)
    label[valid] = np.where(d[valid] < INITIATION_LAG_DAYS, 'INITIATION', 'AFTER_INITIATION')
    return label


def intra_run_split_points(d, u, intra_recovery=0.15):
    """Detect every intra-run recovery jump: a place where the 7-day rolling mean of
    U_relative rises by more than `intra_recovery` within one nominal run (an undetected
    minor clean that didn't trigger a full TAM/shell-switch run boundary upstream).

    Single canonical detector -- both `robust_fouling_rate` (splits at only the LAST cut,
    keeping the current sub-run for its authoritative scalar rate) and
    `segment_fouling_rates` (splits at EVERY cut, for visualization/QA) call this, and the
    notebook's chart markers are sourced from the same segment boundaries, so the annotated
    "minor clean" markers can never disagree with what actually drove the fit.

    `d`, `u` must already be the lag/spike/winsorize-filtered arrays a fit would use (same
    array `robust_fouling_rate` operates on at this point in its own pipeline). Returns a
    sorted array of cut days (empty if none found)."""
    d = np.asarray(d, float)
    u = np.asarray(u, float)
    if len(u) < 8:
        return np.array([])
    order = np.argsort(d)
    du = np.diff(pd.Series(u[order]).rolling(7, min_periods=3, center=True).mean().values)
    jumps = np.where(du > intra_recovery)[0]
    if not len(jumps):
        return np.array([])
    return np.sort(d[order][jumps + 1])


def _fit_segment(d1, u1, rf1, min_span_days=30, min_pts=20, recent_days=60,
                  slope_tol=5e-4, min_r2_gate=0.30, max_sign_change_rate=0.35):
    """Given ONE already-filtered (lag/spike/winsorize/split) days_on_duty/u_relative/rf_run
    segment, run the Theil-Sen baseline + AIC-race (linear/asymptotic/power) curve fit and the
    reliability gate. Extracted so `robust_fouling_rate` (fits only the tail segment after the
    last intra-run recovery) and `segment_fouling_rates` (fits EVERY intra-run sub-segment) use
    byte-identical fitting logic -- the former's output is unaffected by this refactor, and the
    latter's last segment always numerically matches the former's output exactly."""
    from scipy import stats
    out = dict(dRf_per_day=None, intercept=None, dRf_ci_lo=None, dRf_ci_hi=None,
               dRf_per_day_recent=None, dUrel_per_day=None, R2=None,
               model_selected=None, dRf_per_day_tail=None, dRf_per_day_wholerun=None,
               tau_days=None, A_asymp=None, Rf_inf_asymp=None, asymp_aic=None, linear_aic=None,
               power_aic=None, R2_model=None, sign_change_rate=None, last_day_on_duty=None,
               reliable=False, rate_flag=None,
               dUrel_per_day_tail=None, dUrel_per_day_wholerun=None)

    span = float(d1.max() - d1.min()) if len(d1) else 0.0
    if span < min_span_days:
        out['rate_flag'] = 'insufficient_span'; return out
    if len(d1) < min_pts:
        out['rate_flag'] = 'few_points'; return out

    order = np.argsort(d1)
    d1s, rf1s = d1[order], rf1[order]

    slope, intercept, lo, hi = stats.theilslopes(rf1, d1)
    pred = intercept + slope * d1
    ss_tot = float(np.sum((rf1 - rf1.mean()) ** 2))
    r2 = 1 - float(np.sum((rf1 - pred) ** 2)) / ss_tot if ss_tot > 0 else 0.0

    # AIC race: linear vs rising-asymptote (Kern-Seaton) vs power-law -- see
    # robust_fouling_rate's docstring for why power is in the race and the exponent
    # plausibility guard (curve_fit can converge to a numerically-degenerate near-zero
    # coefficient / huge exponent local optimum with a wildly unstable tail derivative).
    fit_lin = cm.fit_model('linear', d1s, rf1s, models=cm.MODELS_RISING)
    fit_asy = cm.fit_model('asymptotic', d1s, rf1s, models=cm.MODELS_RISING)
    fit_pow = cm.fit_model('power', d1s, rf1s, models=cm.MODELS_RISING)
    if fit_pow is not None and not (0.15 <= abs(fit_pow['params'][1]) <= 6.0):
        fit_pow = None
    # Second, independent plausibility guard: even an exponent inside [0.15, 6] can still
    # pair with a numerically-collapsed near-zero coefficient, producing a "hockey stick"
    # curve that's visually flat for most of the run and only rises in the final stretch
    # (confirmed empirically: E108AB Run4, a=2.4e-12/b=3.47 -- flat 0.0044 from day 20 to
    # ~300, then rises to 0.018 by day 622; visually indistinguishable from a fitting bug).
    # `growth_ratio` = (t_end/t_start)^b is the power term's own multiplicative growth
    # across the fitted window -- a direct, unit-free measure of how "hockey-stick" shaped
    # the curve is, independent of the coefficient's absolute scale. Calibrated empirically
    # against every power-model reliable run in the production dataset: legitimate
    # accelerating fits (E101AB b=1.73, E110ABC b=2.12, ...) topped out at ~9.5e3; the two
    # confirmed-degenerate fits (E108AB Run4, E109AB Run2) were 1.5e5 and 7.2e7 -- orders of
    # magnitude past every legitimate case, with a wide margin either side of this cutoff.
    if fit_pow is not None:
        t_start_pow, t_end_pow = d1s[0], d1s[-1]
        b_pow = fit_pow['params'][1]
        growth_ratio = (t_end_pow / max(t_start_pow, 1.0)) ** abs(b_pow)
        if growth_ratio > 3e4:
            fit_pow = None
    fits = [f for f in (fit_lin, fit_asy, fit_pow) if f]
    best = min(fits, key=lambda f: f['aic']) if fits else None

    if best is not None and best['name'] in ('asymptotic', 'power'):
        model_selected = best['name']
        dRf_tail = cm.tail_slope(model_selected, best['params'], d1s[-1], models=cm.MODELS_RISING)
        p1, p2, p3 = best['params']
        tau_days = float(p2)
        rf_inf_asymp = float(p3)
        a_asymp = float(p1)
        pred_sel = cm.MODELS_RISING[model_selected][0](d1s, *best['params'])
    else:
        model_selected = 'linear'
        dRf_tail = float(slope)
        tau_days = None
        rf_inf_asymp = None
        a_asymp = None
        pred_sel = intercept + slope * d1s
    ss_tot_sel = float(np.sum((rf1s - rf1s.mean()) ** 2))
    r2_model = 1 - float(np.sum((rf1s - pred_sel) ** 2)) / ss_tot_sel if ss_tot_sel > 0 else 0.0

    roll = pd.Series(rf1s).rolling(7, min_periods=3, center=True).mean().to_numpy()
    dsig = np.sign(np.diff(roll))
    dsig = dsig[np.isfinite(dsig) & (dsig != 0)]
    sign_change_rate = float(np.mean(np.diff(dsig) != 0)) if len(dsig) > 1 else 0.0

    rec = d1 >= (d1.max() - recent_days)
    slope_recent = stats.theilslopes(rf1[rec], d1[rec])[0] if rec.sum() >= max(8, min_pts // 2) else None
    slope_urel = float(stats.theilslopes(u1, d1)[0])   # secondary cross-check, always simple Theil-Sen

    out.update(dRf_per_day=round(float(dRf_tail), 8),
               intercept=round(float(intercept), 8),
               dRf_ci_lo=round(float(lo), 8), dRf_ci_hi=round(float(hi), 8),
               dRf_per_day_recent=(round(float(slope_recent), 8) if slope_recent is not None else None),
               dUrel_per_day=round(slope_urel, 6),
               dUrel_per_day_tail=round(slope_urel, 6),
               dUrel_per_day_wholerun=round(slope_urel, 6),
               R2=round(float(r2), 3),
               model_selected=model_selected,
               dRf_per_day_tail=round(float(dRf_tail), 8),
               dRf_per_day_wholerun=round(float(slope), 8),
               tau_days=(round(tau_days, 2) if tau_days is not None else None),
               A_asymp=(round(a_asymp, 8) if a_asymp is not None else None),
               Rf_inf_asymp=(round(rf_inf_asymp, 6) if rf_inf_asymp is not None else None),
               asymp_aic=(round(fit_asy['aic'], 2) if fit_asy else None),
               linear_aic=(round(fit_lin['aic'], 2) if fit_lin else None),
               power_aic=(round(fit_pow['aic'], 2) if fit_pow else None),
               R2_model=round(float(r2_model), 3),
               sign_change_rate=round(sign_change_rate, 3),
               last_day_on_duty=round(float(d1s[-1]), 2))

    if slope <= 0 or lo <= -slope_tol:
        out['rate_flag'] = 'negative_slope_recovery' if slope < -slope_tol else 'flat_no_signal'
        return out
    if r2_model < min_r2_gate:
        out['rate_flag'] = 'noisy_low_r2'; return out
    if sign_change_rate > max_sign_change_rate:
        out['rate_flag'] = 'oscillating'; return out
    if slope_urel > slope_tol:   # Rf rising but U_relative also rising -> inconsistent
        out['rate_flag'] = 'urel_inconsistent'; return out
    out['reliable'] = True; out['rate_flag'] = 'ok'
    return out


def robust_fouling_rate(days_on_duty, u_relative, rf_run=None, state=None,
                        lag_days=INITIATION_LAG_DAYS, winsor_ceil=1.10, recent_days=60,
                        min_span_days=30, min_pts=20, min_normal_frac=0.5,
                        slope_tol=5e-4, intra_recovery=0.15, inservice_states=INSERVICE_STATES,
                        min_r2_gate=0.30, max_sign_change_rate=0.35):
    """Physically-grounded, robust per-run fouling-rate estimate for ONE run's on-duty window.

    PRIMARY metric is Rf (fouling resistance, m^2*K/W), not U_relative (changed 2026-07-19).
    Rf is the quantity the mechanistic fouling literature actually works in -- Kern & Seaton
    (1959)'s asymptotic model, TEMA design fouling factors, and every Rf-based paper this
    project reviewed (Hosseini et al. 2022's sqrt(Rf) transform, Biyanto et al. 2014's
    Kern-Seaton scheduling model) are all formulated in Rf(t), because Rf is the physically
    additive resistance (1/U = 1/U_clean + Rf) that grows with deposit thickness. U_relative
    (=U/U_clean, dimensionless, cross-HX comparable) is a real practical/industrial monitoring
    convention (a "cleanliness factor"), but it is a NONLINEAR, saturating transform of Rf
    (U_relative = 1/(1 + Rf*U_clean) -- see production/02_hx_performance_operating_modes.ipynb
    Section 3.5b for the empirical check) -- not an independent signal, and not the metric the
    literature treats as fundamental. It is now the SECONDARY sign-consistency cross-check.

    Fixes the failure modes of a plain OLS-per-run on U_relative (see METHODOLOGY §3.5), now
    mirrored in Rf-space:
      * NORMAL-state mask   — drop points where the HX is SUBSTITUTED/BYPASS/OFFLINE
                              (not the active shell) so its trend reflects real service only.
      * winsorize            — floor Rf at 0 wherever U_relative's own winsorize trigger
                              (U_relative > winsor_ceil, ~10% "cleaner than clean") fires --
                              those points are baseline-too-low/throughput artifacts in EITHER
                              unit, not genuine negative fouling resistance.
      * Theil-Sen slope     — median-of-pairwise-slopes (breakdown ~29%) on Rf, robust to
                              spikes OLS chokes on; returns a 95% CI. The robust linear
                              baseline used for the sign/CI reliability gate.
      * curve refit         — Rf rarely grows as one straight line for an entire run: some HX
                              show a fast initial rise (film formation) that flattens toward a
                              mature fouling-resistance ceiling Rf_inf (Kern-Seaton form, the
                              textbook Rf(t)=Rf_inf*(1-exp(-t/tau)) shape -- MODELS_RISING's
                              'asymptotic'); others show genuinely ACCELERATING growth over the
                              observed run (power-law, Rf(t)=a*t^b+c with b>1 -- confirmed
                              empirically, e.g. E101AB/E110ABC, not assumed). An AIC race between
                              linear / asymptotic / power (see curve_models.py, shared with the
                              PHM engine) picks whichever shape actually fits, so a short/still-
                              linear run isn't force-fit to a curve it doesn't need, and a run
                              that doesn't decelerate isn't force-fit to a Kern-Seaton ceiling it
                              never approaches (that previously degenerated to tau->inf trying to
                              fake a straight line, and visibly failed to track the data).
      * tail-slope rate     — the reported `dRf_per_day` is the CURRENT rate: the analytic
                              derivative of the winning curve at the run's most recent point
                              (equals the Theil-Sen slope when linear wins). This is what "how
                              fast is this HX fouling right now" should mean for ranking/RUL —
                              a whole-run average slope under-reads the current rate for a run
                              that has already flattened toward its asymptote.
      * oscillation gate     — sign-change frequency of the smoothed derivative + a model-fit R²
                              floor catch runs dominated by operational noise (e.g. repeated
                              shell-switch cycling) that a sign-of-slope-only check can miss,
                              regardless of whether the noisy segment nets a positive Rf slope.
      * U_relative cross-check — Theil-Sen slope of U_relative (must be <=0 physically) for a
                              sign-consistency gate (dRf>0 <-> dU_rel<0).
      * recent-window rate  — Theil-Sen over the last `recent_days` on-duty days, kept as a
                              secondary diagnostic cross-check against the tail-slope estimate.
      * reliability gate    — a fouling rate is only `reliable` if the whole-run Rf trend is
                              significantly POSITIVE (CI lower bound > -slope_tol), the
                              selected-model fit is not noise-dominated (R² floor,
                              sign-change-rate ceiling), span/points/NORMAL-fraction suffice,
                              and U_relative agrees; else `rate_flag` says why and it is
                              EXCLUDED downstream rather than emitting an unphysical number.

    Inputs are array-likes for a single run (same length/order). `state` optional; `rf_run`
    is REQUIRED for a reliable result (returns `rate_flag='no_rf_data'` if omitted, since Rf
    is now the primary fitted quantity -- U_relative alone can no longer establish reliability).
    Returns a dict of the CSV columns (values None when not computable)."""
    from scipy import stats
    d = np.asarray(days_on_duty, float)
    u = np.asarray(u_relative, float)
    rf = np.asarray(rf_run, float) if rf_run is not None else None

    fin = np.isfinite(d) & np.isfinite(u) & (d >= lag_days)
    if rf is not None:
        fin = fin & np.isfinite(rf)
    st = np.asarray(state) if state is not None else None
    in_service = np.isin(st, list(inservice_states)) if st is not None else None
    normal_frac = float(in_service[fin].mean()) if (st is not None and fin.sum()) else 1.0
    keep = fin & in_service if st is not None else fin

    d1, u1 = d[keep], u[keep]
    rf1 = rf[keep] if rf is not None else None

    out = dict(dRf_per_day=None, intercept=None, dRf_ci_lo=None, dRf_ci_hi=None,
               dRf_per_day_recent=None, dUrel_per_day=None, R2=None,
               N_regression_pts=int(len(d1)), span_days=round(float(d1.max() - d1.min()), 1) if len(d1) else 0.0,
               normal_frac=round(normal_frac, 3), n_winsorized=0,
               split_after_day=None,
               model_selected=None, dRf_per_day_tail=None, dRf_per_day_wholerun=None,
               tau_days=None, A_asymp=None, Rf_inf_asymp=None, asymp_aic=None, linear_aic=None,
               power_aic=None,
               R2_model=None, sign_change_rate=None, last_day_on_duty=None,
               reliable=False, rate_flag=None,
               # back-compat aliases: dUrel_per_day no longer gets its own curve fit (U_relative
               # is now the secondary check, always a plain Theil-Sen slope), so "tail" and
               # "wholerun" collapse to the same number -- kept as separate columns only because
               # existing consumers (compute_fouling_rate.py's column list) already read them.
               dUrel_per_day_tail=None, dUrel_per_day_wholerun=None)

    if rf1 is None:
        out['rate_flag'] = 'no_rf_data'
        return out

    # data-sufficiency gate (physical trend can't be read from too little in-service data);
    # span/point-count gates are applied further below, AFTER spike/winsor/split filtering,
    # against the actual thresholds (min_span_days/min_pts) rather than a hardcoded minimum --
    # an empty/near-empty `d1` here (e.g. a run shorter than lag_days) falls through safely
    # since every block below is itself guarded by `if len(...) >= 8`.
    if normal_frac < min_normal_frac:
        out['rate_flag'] = 'substituted_dominated'; return out

    # isolated single-day spike guard: a raw Rf value far BELOW both temporal neighbors (the
    # mirror image of a U_relative spike far ABOVE its neighbors -- same underlying sensor
    # glitch, viewed in the other unit) is not physical -- a fouling film doesn't dissolve and
    # reform within a day. Reject it outright rather than winsorize-clip: clipping still injects
    # a point at the floor into the regression, which for a spike deep into an already-fouled
    # run drags the fit far off the surrounding data (same failure mode previously confirmed on
    # E113A Run6 2021-10-24 in U_relative terms).
    order0 = np.argsort(d1)
    roll_med_rf = pd.Series(rf1[order0]).rolling(7, min_periods=3, center=True).median().to_numpy()
    dev_rf = rf1[order0] - roll_med_rf
    u_winsor_trigger_sorted = u1[order0] > winsor_ceil
    spike_sorted = np.isfinite(dev_rf) & (dev_rf < -0.3 * np.nanmedian(np.abs(roll_med_rf[np.isfinite(roll_med_rf)]))
                                          if np.isfinite(roll_med_rf).any() else False) & u_winsor_trigger_sorted
    spike = np.zeros(len(d1), dtype=bool)
    spike[order0[spike_sorted]] = True
    if spike.any():
        d1, u1, rf1 = d1[~spike], u1[~spike], rf1[~spike]

    # winsorize: wherever U_relative's own calibrated trigger (>winsor_ceil, ~10% "cleaner
    # than clean") fires, floor Rf at 0 -- reuses the existing dimensionless-calibrated
    # threshold rather than re-deriving an Rf-specific one (which would need U_clean, not
    # available in this function's signature).
    winsor_mask = u1 > winsor_ceil
    n_wins = int(winsor_mask.sum())
    rf1 = np.where(winsor_mask, np.minimum(rf1, 0.0), rf1)
    u1 = np.clip(u1, None, winsor_ceil)

    # intra-run cleaning guard: if U_relative jumps UP mid-run (an undetected clean/recovery),
    # never regress across it in EITHER unit -- keep only the segment AFTER the LAST such jump
    # (the current sub-run). `segment_fouling_rates` uses the same `intra_run_split_points`
    # detector to fit EVERY sub-segment instead of discarding all but the tail, for
    # visualization/QA -- this function's own scalar output is unaffected by that.
    cuts = intra_run_split_points(d1, u1, intra_recovery=intra_recovery)
    split_at = float(cuts[-1]) if len(cuts) else None
    if split_at is not None:
        seg = d1 >= split_at
        d1, u1, rf1 = d1[seg], u1[seg], rf1[seg]
    span = float(d1.max() - d1.min()) if len(d1) else 0.0
    out['span_days'] = round(span, 1)
    out['n_winsorized'] = n_wins
    out['split_after_day'] = round(split_at, 1) if split_at is not None else None

    seg_result = _fit_segment(d1, u1, rf1, min_span_days=min_span_days, min_pts=min_pts,
                               recent_days=recent_days, slope_tol=slope_tol,
                               min_r2_gate=min_r2_gate, max_sign_change_rate=max_sign_change_rate)
    out.update(seg_result)
    return out


def segment_fouling_rates(days_on_duty, u_relative, rf_run, state=None,
                          lag_days=INITIATION_LAG_DAYS, winsor_ceil=1.10, recent_days=60,
                          min_span_days=30, min_pts=20, min_normal_frac=0.5,
                          slope_tol=5e-4, intra_recovery=0.15, inservice_states=INSERVICE_STATES,
                          min_r2_gate=0.30, max_sign_change_rate=0.35):
    """Like `robust_fouling_rate`, but returns a fit for EVERY intra-run sub-segment (split at
    every detected minor-clean recovery jump via `intra_run_split_points`), not just the tail
    segment after the last one. Diagnostic/visualization use only: the authoritative per-run
    scalar rate used by ranking/RUL/dashboard consumers comes from `robust_fouling_rate`
    (unchanged by this function's existence) and always numerically equals this function's
    LAST segment, since both share the identical prep pipeline and `_fit_segment` fitting code.

    Returns a list of dicts (oldest segment first), each shaped like `robust_fouling_rate`'s
    return dict plus `seg_index`/`seg_start_day`/`seg_end_day`/`N_regression_pts`."""
    d = np.asarray(days_on_duty, float)
    u = np.asarray(u_relative, float)
    rf = np.asarray(rf_run, float)

    fin = np.isfinite(d) & np.isfinite(u) & np.isfinite(rf) & (d >= lag_days)
    st = np.asarray(state) if state is not None else None
    in_service = np.isin(st, list(inservice_states)) if st is not None else None
    normal_frac = float(in_service[fin].mean()) if (st is not None and fin.sum()) else 1.0
    keep = fin & in_service if st is not None else fin
    d1, u1, rf1 = d[keep], u[keep], rf[keep]

    if normal_frac < min_normal_frac or len(d1) == 0:
        return [dict(seg_index=0, seg_start_day=None, seg_end_day=None, N_regression_pts=int(len(d1)),
                     reliable=False, rate_flag=('substituted_dominated' if len(d1) else 'no_data'))]

    # spike guard + winsorize: identical to robust_fouling_rate's own copy, applied ONCE up
    # front (shared across every sub-segment) rather than per-segment, so segmenting a run
    # doesn't change how spikes/winsorize are judged near a cut boundary.
    order0 = np.argsort(d1)
    roll_med_rf = pd.Series(rf1[order0]).rolling(7, min_periods=3, center=True).median().to_numpy()
    dev_rf = rf1[order0] - roll_med_rf
    u_winsor_trigger_sorted = u1[order0] > winsor_ceil
    spike_sorted = np.isfinite(dev_rf) & (dev_rf < -0.3 * np.nanmedian(np.abs(roll_med_rf[np.isfinite(roll_med_rf)]))
                                          if np.isfinite(roll_med_rf).any() else False) & u_winsor_trigger_sorted
    spike = np.zeros(len(d1), dtype=bool)
    spike[order0[spike_sorted]] = True
    if spike.any():
        d1, u1, rf1 = d1[~spike], u1[~spike], rf1[~spike]

    winsor_mask = u1 > winsor_ceil
    rf1 = np.where(winsor_mask, np.minimum(rf1, 0.0), rf1)
    u1 = np.clip(u1, None, winsor_ceil)

    cuts = intra_run_split_points(d1, u1, intra_recovery=intra_recovery)
    bounds = [float(d1.min())] + [float(c) for c in cuts] + [float(d1.max()) + 1.0]

    segments = []
    for i in range(len(bounds) - 1):
        seg_mask = (d1 >= bounds[i]) & (d1 < bounds[i + 1])
        d_seg, u_seg, rf_seg = d1[seg_mask], u1[seg_mask], rf1[seg_mask]
        res = _fit_segment(d_seg, u_seg, rf_seg, min_span_days=min_span_days, min_pts=min_pts,
                            recent_days=recent_days, slope_tol=slope_tol,
                            min_r2_gate=min_r2_gate, max_sign_change_rate=max_sign_change_rate)
        res['seg_index'] = i
        res['seg_start_day'] = round(bounds[i], 1)
        res['seg_end_day'] = round(float(d_seg.max()), 1) if len(d_seg) else round(bounds[i + 1], 1)
        res['N_regression_pts'] = int(len(d_seg))
        segments.append(res)
    return segments


def quality_gate_runs(fr_df, min_r2=0.3, min_pts=10):
    """NON-AUTHORITATIVE diagnostic only. The canonical reliability decision is the `reliable`
    column already produced by `robust_fouling_rate` (R²/oscillation/sign/span/Rf gates all
    applied there) — this helper does NOT redefine it. It exists purely to report how an
    R²/N-only heuristic would have differed, for debugging/QA, and adds `rate_reliable` as a
    separate diagnostic column so it's never mistaken for the real gate. Do not consume
    `rate_reliable` downstream — consume `reliable`."""
    df = fr_df.copy()
    r2 = df.get('R2', pd.Series(1.0, index=df.index)).fillna(0)
    npts = df.get('N_regression_pts', pd.Series(min_pts, index=df.index)).fillna(0)
    df['rate_reliable'] = (r2 >= min_r2) & (npts >= min_pts)
    canonical = df.get('reliable')
    summ = dict(total=len(df), reliable=int(df['rate_reliable'].sum()),
                flagged=int((~df['rate_reliable']).sum()), min_r2=min_r2, min_pts=min_pts)
    if canonical is not None:
        summ['canonical_reliable'] = int(canonical.sum())
        summ['disagrees_with_canonical'] = int((df['rate_reliable'] != canonical.fillna(False)).sum())
    return df, summ
