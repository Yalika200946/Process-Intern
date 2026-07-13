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


def robust_fouling_rate(days_on_duty, u_relative, rf_run=None, state=None,
                        lag_days=15, winsor_ceil=1.10, recent_days=60,
                        min_span_days=30, min_pts=20, min_normal_frac=0.5,
                        slope_tol=5e-4, intra_recovery=0.15, inservice_states=INSERVICE_STATES):
    """Physically-grounded, robust per-run fouling-rate estimate for ONE run's on-duty window.

    Fixes the failure modes of a plain OLS-per-run on U_relative (see METHODOLOGY §3.5):
      * NORMAL-state mask   — drop points where the HX is SUBSTITUTED/BYPASS/OFFLINE
                              (not the active shell) so its trend reflects real service only.
      * winsorize high-side — clip U_relative to `winsor_ceil` (~1.10); values above are
                              baseline-too-low / throughput artifacts, not "cleaner than clean".
      * Theil-Sen slope     — median-of-pairwise-slopes (breakdown ~29%), robust to the
                              U_relative spikes OLS chokes on; returns a 95% CI.
      * Rf cross-check      — slope of fouling resistance Rf (must be ≥0 physically) for a
                              sign-consistency gate (dU_rel<0 ⇄ dRf>0).
      * recent-window rate  — Theil-Sen over the last `recent_days` on-duty days = the CURRENT
                              rate (whole-run slope under-reads long/asymptotic runs).
      * reliability gate    — a fouling rate is only `reliable` if the trend is significantly
                              NEGATIVE (CI upper < slope_tol), the span/points/NORMAL-fraction
                              suffice, and Rf agrees; else `rate_flag` says why and it is
                              EXCLUDED downstream rather than emitting an unphysical number.

    Inputs are array-likes for a single run (same length/order). `state`/`rf_run` optional.
    Returns a dict of the CSV columns (values None when not computable)."""
    from scipy import stats
    d = np.asarray(days_on_duty, float)
    u = np.asarray(u_relative, float)
    fin = np.isfinite(d) & np.isfinite(u) & (d >= lag_days)
    st = np.asarray(state) if state is not None else None
    in_service = np.isin(st, list(inservice_states)) if st is not None else None
    normal_frac = float(in_service[fin].mean()) if (st is not None and fin.sum()) else 1.0
    keep = fin & in_service if st is not None else fin

    d1, u1 = d[keep], u[keep]
    rf1 = np.asarray(rf_run, float)[keep] if rf_run is not None else None
    n_wins = int((u1 > winsor_ceil).sum()) if len(u1) else 0
    u1 = np.clip(u1, None, winsor_ceil)

    # intra-run cleaning guard: if U_relative jumps UP mid-run (an undetected clean/recovery),
    # never regress across it — keep only the segment AFTER the last such jump (the current
    # sub-run). Directly prevents a trend line spanning a recovery (complaint #3).
    split_at = None
    if len(u1) >= 8:
        order = np.argsort(d1)
        du = np.diff(pd.Series(u1[order]).rolling(7, min_periods=3, center=True).mean().values)
        jumps = np.where(du > intra_recovery)[0]
        if len(jumps):
            cut = d1[order][jumps[-1] + 1]
            split_at = float(cut)
            seg = d1 >= cut
            d1, u1 = d1[seg], u1[seg]
            if rf1 is not None:
                rf1 = rf1[seg]
    span = float(d1.max() - d1.min()) if len(d1) else 0.0

    out = dict(dUrel_per_day=None, intercept=None, dUrel_ci_lo=None, dUrel_ci_hi=None,
               dUrel_per_day_recent=None, dRf_per_day=None, R2=None,
               N_regression_pts=int(len(d1)), span_days=round(span, 1),
               normal_frac=round(normal_frac, 3), n_winsorized=n_wins,
               split_after_day=(round(split_at, 1) if split_at is not None else None),
               reliable=False, rate_flag=None)

    # data-sufficiency gates (physical trend can't be read from too little in-service data)
    if normal_frac < min_normal_frac:
        out['rate_flag'] = 'substituted_dominated'; return out
    if span < min_span_days:
        out['rate_flag'] = 'insufficient_span'; return out
    if len(d1) < min_pts:
        out['rate_flag'] = 'few_points'; return out

    slope, intercept, lo, hi = stats.theilslopes(u1, d1)
    pred = intercept + slope * d1
    ss_tot = float(np.sum((u1 - u1.mean()) ** 2))
    r2 = 1 - float(np.sum((u1 - pred) ** 2)) / ss_tot if ss_tot > 0 else 0.0

    rec = d1 >= (d1.max() - recent_days)
    slope_recent = stats.theilslopes(u1[rec], d1[rec])[0] if rec.sum() >= max(8, min_pts // 2) else None
    slope_rf = None
    if rf1 is not None and np.isfinite(rf1).sum() >= min_pts:
        mrf = np.isfinite(rf1)
        slope_rf = float(stats.theilslopes(rf1[mrf], d1[mrf])[0])

    out.update(dUrel_per_day=round(float(slope), 6),
               intercept=round(float(intercept), 6),
               dUrel_ci_lo=round(float(lo), 6), dUrel_ci_hi=round(float(hi), 6),
               dUrel_per_day_recent=(round(float(slope_recent), 6) if slope_recent is not None else None),
               dRf_per_day=(round(slope_rf, 8) if slope_rf is not None else None),
               R2=round(float(r2), 3))

    # physical + reliability constraint: a genuine fouling run has U_relative STRICTLY declining
    # (slope<0) with a CI whose upper bound is still essentially negative (< slope_tol).
    if slope >= 0 or hi >= slope_tol:
        out['rate_flag'] = 'positive_slope_throughput' if slope > slope_tol else 'flat_no_signal'
        return out
    if slope_rf is not None and slope_rf < -slope_tol:   # U falling but Rf also falling → inconsistent
        out['rate_flag'] = 'rf_inconsistent'; return out
    out['reliable'] = True; out['rate_flag'] = 'ok'
    return out


def quality_gate_runs(fr_df, min_r2=0.3, min_pts=10):
    """Flag per-run fouling-rate estimates that are too weak to trust (low R²/few points).
    Adds `rate_reliable` + returns (df, summary). Use so weak runs are down-weighted/flagged,
    not treated equal to well-fit ones."""
    df = fr_df.copy()
    r2 = df.get('R2', pd.Series(1.0, index=df.index)).fillna(0)
    npts = df.get('N_regression_pts', pd.Series(min_pts, index=df.index)).fillna(0)
    df['rate_reliable'] = (r2 >= min_r2) & (npts >= min_pts)
    summ = dict(total=len(df), reliable=int(df['rate_reliable'].sum()),
                flagged=int((~df['rate_reliable']).sum()), min_r2=min_r2, min_pts=min_pts)
    return df, summ
