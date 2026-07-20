"""
PHM analysis engine — Prognostics & Health Management for the CPHT fouling problem.

Computes and exports (dashboard/data/*.json + Data/*.csv):
  C1 propagation_models.json  multi-model degradation fit per HX + out-of-sample backtest
  C2 rul.json                 Monte-Carlo RUL distribution (P10/P50/P90, P(clean<=N days))
  C3 reliability.json         Weibull survival: hazard rate, reliability R(t), P(clean in N)
  C4 drivers.json             which operating variables drive fouling rate (SHAP) + levers

Honest by construction (same discipline as the persistence finding): per-HX Weibull
uses pooled shape when runs are few (flagged low-confidence); backtest is leave-part-of-run-out
(out-of-sample); driver analysis reports CV R2 + n and never claims causation.

Run: python pipeline/phm_analysis.py
"""
import os
import warnings, json, sys
warnings.filterwarnings('ignore')
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import gamma as gammafn

REPO = Path(__file__).resolve().parent.parent
NB   = REPO / 'notebooks'
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
DASH = REPO / 'dashboard' / 'data'
sys.path.append(str(REPO))
from src.models import phm_config as C
from src.models.fouling_curves import MODELS_RISING as MODELS, fit_model, predict_cross
from src.validation.nb_audit import classify_rate_source, leave_run_out_cv
from src.validation import threshold_backtest as TB
from src.models import survival as SV
from src.models import uncertainty as UN

rng = np.random.default_rng(C.RANDOM_SEED)

# ---------------- load ----------------
# Canonical degradation signal produced by notebook 06 and consumed by notebook 07.
# The former Cold_Out file can remain on disk from an older run and has different units.
dev = pd.read_csv(DATA / 'Q_Deviation_Signal.csv', parse_dates=['Timestamp'])
ttc = pd.read_csv(DATA / 'Time_To_Clean_Prediction.csv').set_index('HX')
if 'rate_kW_per_day' not in ttc.columns and 'rate_degC_per_day' in ttc.columns:
    # Transitional compatibility for artifacts generated before the unit-name fix.
    # Values were already Q-duty kW/day; only the legacy column label was wrong.
    ttc = ttc.rename(columns={'rate_degC_per_day': 'rate_kW_per_day'})
fr  = pd.read_csv(DATA / 'Fouling_Rate_By_Run.csv')
crude = pd.read_csv(DATA / 'Crude_property_profiled.csv', parse_dates=['Date']).set_index('Date').sort_index()
HXES = sorted(dev['HX'].dropna().unique())

# Event/censoring taxonomy (ข้อ 11), consumed by the threshold-crossing backtest (ข้อ 5).
# Written by pipeline/build_event_table.py -- NOT YET reordered ahead of phm_analysis.py in
# run_all.py's POST list (that reorder is ข้อ 12's job, since C3's censored survival refit is
# what actually REQUIRES the ordering guarantee). Until then, tolerate a missing/stale file on
# a partial/first-run so C1 degrades to "treat every completed run as non-censored" rather than
# crashing -- exactly the old behavior's implicit assumption, now explicit and logged.
_event_table_csv = DATA / 'Event_Table.csv'
if _event_table_csv.exists():
    event_table = pd.read_csv(_event_table_csv)
else:
    print('  [C1] Event_Table.csv not found -- run pipeline/build_event_table.py first; '
          'backtest will treat every completed run as non-censored (no threshold-crossing exclusions).')
    event_table = pd.DataFrame(columns=['HX', 'Run', 'censored'])

# P&ID topology (ข้อ 8's partial-pooling similarity source) -- written by
# src/reporting/dashboard_topology.py, which already runs earlier in run_all.py's POST list.
# Graceful fallback (empty dict -> topology_similar_hx returns []) so a partial/--only run
# doesn't hard-crash C2 if this file happens to be missing.
_topo_json_path = DASH / 'pfd_topology.json'
topo_json = json.loads(_topo_json_path.read_text(encoding='utf-8')) if _topo_json_path.exists() else {}
if not topo_json:
    print('  [C2] pfd_topology.json not found -- partial pooling will use own-HX data only (no topology similarity).')

# current run_id per HX (last run_id seen in the deviation-signal series) -- shared by C1/C2
# so both key their 4-state rate-evidence classification (ข้อ 2) off the SAME "current run".
CUR_RUN_BY_HX = {}
for _hx in HXES:
    _d = dev[(dev.HX == _hx)].dropna(subset=['run_id'])
    if not _d.empty:
        CUR_RUN_BY_HX[_hx] = _d['run_id'].unique()[-1]

# degradation model library (C1) — linear/asymptotic/power fit + AIC selection now live in
# src/models/fouling_curves.py (shared with src/validation/nb_audit.py's U_relative fouling-rate estimator).

def gp_fit_predict(t, y, t_query):
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import RBF, ConstantKernel as Ck, WhiteKernel
    kern = Ck(1.0) * RBF(length_scale=max(t.std(), 5)) + WhiteKernel(noise_level=np.var(y)*0.1+1e-6)
    gp = GaussianProcessRegressor(kernel=kern, normalize_y=True, n_restarts_optimizer=0)
    gp.fit(t.reshape(-1, 1), y)
    mu, sd = gp.predict(t_query.reshape(-1, 1), return_std=True)
    return mu, sd

# ---------------- C1: per-HX model comparison + threshold-crossing backtest (ข้อ 5-7) ----------------
def run_c1():
    out = {}
    thresholds = {hx: float(ttc.loc[hx, 'threshold']) for hx in HXES if hx in ttc.index}
    # shared backtest table: multi-origin (30/50/70%), predicts the HX's own APPROVED
    # threshold crossing (not the run's arbitrary end point), naive baselines scored
    # alongside the fitted curves, censored (TAM/mode_transition/never-crossed) runs
    # excluded from point-error automatically (see threshold_backtest.py docstring).
    bt_df = TB.run_threshold_backtest(dev, fr, thresholds, event_table, HXES, list(MODELS),
                                      fractions=C.BACKTEST_ORIGIN_FRACTIONS, min_run_pts=C.MIN_RUN_PTS)
    metrics_hx = TB.summarize_metrics(bt_df, group_cols=('HX', 'predictor'))     # per-HX, for the ข้อ 7 gate
    metrics = TB.summarize_metrics(bt_df, group_cols=('predictor',))            # pooled, for the headline table
    bias = TB.bias_metrics(bt_df, group_cols=('predictor',))
    acc = TB.accuracy_within(bt_df, group_cols=('predictor',))
    fam = TB.false_alarm_missed_warning_rates(bt_df, warn_horizon_days=C.NEAR_THRESHOLD_DAYS, group_cols=('predictor',))
    cov = TB.interval_coverage(bt_df)

    for hx in HXES:
        d = dev[(dev.HX == hx)].dropna(subset=['run_id'])
        if d.empty:
            continue
        runs = d['run_id'].unique()
        cur_run = runs[-1]
        cur = d[d.run_id == cur_run].sort_values('days_on_duty')
        t = cur['days_on_duty'].to_numpy(float); y = cur['deviation'].to_numpy(float)
        thr = thresholds.get(hx, float(np.nanmax(y) * 1.1))
        fits = [fit_model(m, t, y) for m in MODELS if len(t) >= 4]
        fits = [f for f in fits if f]
        best = min(fits, key=lambda f: f['aic']) if fits else None
        # curve for display (downsampled) + best-model projection to threshold
        idx = np.linspace(0, len(t)-1, min(len(t), 40)).astype(int)
        proj_days = predict_cross(best['name'], best['params'], t[-1], thr) if best else None
        # 4-state rate-evidence classification (ข้อ 2): best_proj_days above is fit purely from
        # this run's own deviation curve, independent of the Fouling_Rate_By_Run.csv physics
        # gate -- classify it against that gate too so the dashboard can flag "C1 has a curve fit,
        # but the underlying rate hasn't passed the reliable-run gate" instead of showing a bare date.
        cls_state, _ = classify_rate_source(fr, hx, CUR_RUN_BY_HX.get(hx))
        best_proj_rate_source = cls_state if cls_state else ('unreliable_current_fit' if best else 'no_forecast')

        # model-selection gate (ข้อ 7): the projection shown to the user must beat every
        # naive baseline's MAE on this HX's own backtest history, not just win AIC.
        hx_mae = {predictor: v['mae_days'] for (hx2, predictor), v in metrics_hx.items() if hx2 == hx}
        sel = TB.select_best_model(hx_mae) if hx_mae else dict(best_model=None, beats_all_baselines=None, baseline_mae={})

        out[hx] = dict(
            n_runs=int(len(runs)), current_run_pts=int(len(t)),
            best_model=best['name'] if best else None,
            threshold=round(thr, 2), current_deviation=round(float(y[-1]), 2),
            models=[dict(name=f['name'], aic=round(f['aic'], 1), params=[round(p, 4) for p in f['params']]) for f in fits],
            curve=[dict(t=round(float(t[i]), 1), y=round(float(y[i]), 2)) for i in idx],
            best_proj_days=proj_days, best_proj_rate_source=best_proj_rate_source,
            best_overall_model=sel['best_model'], beats_all_baselines=sel['beats_all_baselines'],
            baseline_comparison=sel['baseline_mae'],
        )

    # backtest block, keyed by predictor (models + baselines) -- pooled across all HX, with a
    # per-HX breakdown nested inside each predictor (per_hx is ALSO surfaced per-HX above via
    # baseline_comparison/best_overall_model, this is the pooled-view counterpart)
    def _unwrap(d, key):
        v = d.get((key,), {})
        return v if v else {}
    backtest_block = dict(
        origins=list(C.BACKTEST_ORIGIN_FRACTIONS),
        per_model={p: {**_unwrap(metrics, p), **_unwrap(bias, p), **_unwrap(acc, p), **_unwrap(fam, p),
                       'per_hx': {hx2: v for (hx2, pred), v in metrics_hx.items() if pred == p}}
                   for p in set(list(MODELS) + TB.BASELINE_NAMES)},
        coverage=cov,
        note='threshold-crossing backtest: fit visible-to-origin (30/50/70%) data, predict date of '
             'crossing the HX\'s own approved threshold; runs ending without crossing (TAM/mode_transition/'
             'censored current run) are censored and excluded from point-error, see event_table.json',
    )
    # legacy keys kept (deprecated, one release cycle) so any not-yet-migrated dashboard read
    # doesn't crash -- values are the new per-model MAE (comparable order of magnitude to the
    # old RMSE), not a silent recompute of the old 60/40 method.
    legacy_bt = {m: backtest_block['per_model'].get(m, {}).get('mae_days') for m in MODELS}
    legacy_bt_n = {m: backtest_block['per_model'].get(m, {}).get('n', 0) for m in MODELS}
    best_overall = min([m for m in legacy_bt if legacy_bt[m] is not None], key=lambda m: legacy_bt[m], default=None)
    return dict(per_hx=out, backtest=backtest_block,
                backtest_rmse_days=legacy_bt, backtest_n=legacy_bt_n, best_overall_model=best_overall,
                note='DEPRECATED top-level fields (backtest_rmse_days/backtest_n/best_overall_model/note) -- '
                     'see `backtest` block for the current threshold-crossing methodology (ข้อ 5-7)')

# ---------------- C2: Monte-Carlo RUL ----------------
def rate_rel_sd(hx):
    sub = fr[fr.HX == hx]['dRf_per_day'].dropna()
    if len(sub) >= 2 and sub.mean() != 0:
        return float(min(abs(sub.std() / sub.mean()), 1.5))
    return C.RATE_REL_SD_FALLBACK

def run_c2():
    out = {}
    # historical per-run rates (dev-space, same units as ttc's rate_kW_per_day), computed
    # once for every HX -- shared input to the ข้อ 8 bootstrap/partial-pooling sampler.
    rates_by_hx = {hx: UN.historical_run_rates(dev, hx, CUR_RUN_BY_HX.get(hx, 10**9)) for hx in HXES}
    for hx in HXES:
        if hx not in ttc.index:
            continue
        row = ttc.loc[hx]
        cur = float(row['current_deviation']); thr = float(row['threshold']); rate = float(row['rate_kW_per_day'])
        # 4-state rate-evidence classification (ข้อ 2): rate above comes from
        # Time_To_Clean_Prediction.csv (a linear tail-fit in Q-shortfall space, not gated by
        # Fouling_Rate_By_Run.csv's `reliable` flag on its own) -- classify it against that
        # physics gate so a P50/prob_30/60/90 for an unreliable current run isn't shown as if
        # it were as trustworthy as one backed by a gated-reliable run.
        cls_state, _ = classify_rate_source(fr, hx, CUR_RUN_BY_HX.get(hx))
        rate_source = cls_state if cls_state else 'unreliable_current_fit'
        if cur >= thr:
            out[hx] = dict(past_threshold=True, p10=0, p50=0, p90=0,
                           **{f'prob_{h}': 100.0 for h in C.HORIZONS},
                           current_deviation=round(cur, 2), threshold=round(thr, 2), rate_source=rate_source)
            continue
        gap = thr - cur
        rsd = rate_rel_sd(hx)   # kept as a diagnostic-only CV figure, not the sampling parameter anymore
        if rate <= 0:
            out[hx] = dict(past_threshold=False, p10=None, p50=None, p90=None,
                           **{f'prob_{h}': 0.0 for h in C.HORIZONS}, stable=True,
                           current_deviation=round(cur, 2), threshold=round(thr, 2), rate=round(rate, 4),
                           rate_source=rate_source)
            continue
        # multi-source uncertainty composition (ข้อ 9, subsumes ข้อ 8's rate bootstrap as one
        # of its sources): joint Monte Carlo over rate-fit, current-signal noise, threshold,
        # and operating-state uncertainty -- see src/models/uncertainty.py's docstring for
        # exactly which sources are data-driven vs. documented ASSUMED fallbacks.
        rul, sources, pool_meta = UN.compose_uncertainty_sources(
            rate, cur, thr, rates_by_hx, hx, topo_json, dev, CUR_RUN_BY_HX.get(hx),
            n_iter=C.MC_ITERS, rng=rng, min_n_for_own_data=C.MIN_N_FOR_OWN_BOOTSTRAP,
            threshold_uncertainty_frac=C.THRESHOLD_UNCERTAINTY_FRAC,
            operating_state_fallback_sd=C.OPERATING_STATE_UNCERTAINTY_FALLBACK_SD)
        uncertainty_method = 'bootstrap_partial_pooled' if sources.get('rate_fit') else 'parametric_normal_fallback'
        p10, p50, p90 = np.percentile(rul, [10, 50, 90])
        out[hx] = dict(past_threshold=False,
                       p10=round(float(p10), 1), p50=round(float(p50), 1), p90=round(float(p90), 1),
                       **{f'prob_{h}': round(float((rul <= h).mean() * 100), 1) for h in C.HORIZONS},
                       current_deviation=round(cur, 2), threshold=round(thr, 2),
                       rate=round(rate, 4), rate_rel_sd=round(rsd, 3), rate_source=rate_source,
                       uncertainty_method=uncertainty_method, uncertainty_sources=sources, **pool_meta)
    return out

# ---------------- C3: censored survival (Kaplan-Meier + Weibull) / hazard (ข้อ 12) ----------------
def run_c3():
    if _event_table_csv.exists() and not event_table.empty:
        et = event_table
        durs = et[['HX', 'duration_days', 'censored']].dropna(subset=['duration_days'])
        durs = durs[durs.duration_days > 0]
        censoring_method = 'kaplan_meier_weibull'
    else:
        # graceful fallback (no Event_Table.csv yet, e.g. a partial/first run): every run
        # treated as observed -- the OLD behavior, but now explicit rather than implicit.
        print('  [C3] Event_Table.csv not found -- run pipeline/build_event_table.py first; '
              'falling back to naive_uncensored (every run treated as an observed failure).')
        durs = fr[['HX', 'Duration_days']].dropna().rename(columns={'Duration_days': 'duration_days'})
        durs = durs[durs.duration_days > 0]
        durs['censored'] = False
        censoring_method = 'naive_uncensored'

    pool_dur = durs['duration_days'].to_numpy(float)
    pool_obs = (~durs['censored'].astype(bool)).to_numpy()
    n_censored_pool = int(durs['censored'].astype(bool).sum())
    _, k_p, s_p, _ = SV.fit_weibull_censored(pool_dur, pool_obs)

    # current age per HX = last days_on_duty of its current run
    age = {}
    for hx in HXES:
        d = dev[dev.HX == hx].dropna(subset=['run_id'])
        if not d.empty:
            cur = d[d.run_id == d['run_id'].unique()[-1]]
            age[hx] = float(cur['days_on_duty'].max())
    def surv(t, k, s): return float(np.exp(-(max(t, 0) / s) ** k))
    def hazard(t, k, s): return float((k / s) * (max(t, 1e-6) / s) ** (k - 1))
    out = {'_pooled': dict(shape=round(k_p, 3), scale=round(s_p, 1),
                           mtbc=round(s_p * gammafn(1 + 1 / k_p), 1), n=int(len(pool_dur)),
                           n_censored=n_censored_pool),
           'censoring_method': censoring_method}
    for hx in HXES:
        sub = durs[durs.HX == hx]
        sub_dur = sub['duration_days'].to_numpy(float)
        sub_obs = (~sub['censored'].astype(bool)).to_numpy()
        n = len(sub_dur)
        n_cens = int((~sub_obs).sum())
        k, s, mtbc, _, conf = SV.per_hx_survival(sub_dur, sub_obs, k_p, s_p, min_n=C.WEIBULL_MIN_N)
        t0 = age.get(hx, 0.0)
        probs = {}
        R0 = surv(t0, k, s)
        for h in C.HORIZONS:
            probs[f'prob_{h}'] = round((1 - (surv(t0 + h, k, s) / R0 if R0 > 1e-9 else 0)) * 100, 1)
        ts = np.linspace(0, C.SURVIVAL_CURVE_DAYS, 60)
        curve = [dict(t=round(float(x), 0), R=round(surv(x, k, s), 4), hz=round(hazard(x, k, s) * 1000, 3)) for x in ts]
        km_curve = []
        if n >= 2:
            try:
                _, km_curve = SV.fit_km(sub_dur, sub_obs)
            except Exception:
                km_curve = []
        out[hx] = dict(shape=round(k, 3), scale=round(s, 1), mtbc=round(mtbc, 1),
                       n_runs=int(n), n_censored=n_cens, confidence=conf, days_on_duty=round(t0, 0),
                       hazard_now_per1000d=round(hazard(t0, k, s) * 1000, 3), **probs,
                       curve=curve, km_curve=km_curve)
    return out

# ---------------- C4: degradation drivers (ข้อ 3: gated on grouped CV beating baseline) ----------------
def run_c4():
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.dummy import DummyRegressor
    from sklearn.preprocessing import StandardScaler
    rows = []
    for hx in HXES:
        d = dev[dev.HX == hx].dropna(subset=['run_id'])
        for r in d['run_id'].unique():
            rr = d[d.run_id == r]
            fr_row = fr[(fr.HX == hx) & (fr.Run == r)]
            if fr_row.empty:
                continue
            rate = float(fr_row['dRf_per_day'].iloc[0])
            if not np.isfinite(rate):
                continue
            dr = rr['Timestamp']
            ca = crude.reindex(pd.date_range(dr.min(), dr.max())).ffill().bfill().mean(numeric_only=True)
            rows.append(dict(HX=hx, target=rate,
                             film_temp=float(((rr['cold_in'] + rr['cold_out']) / 2).mean()),
                             flow=float(rr['cold_flow'].mean()),
                             duration=float(rr['days_on_duty'].max()),
                             **{c: float(ca.get(c, np.nan)) for c in C.CRUDE_FEATURES}))
    df = pd.DataFrame(rows).dropna()
    feats = ['film_temp', 'flow', 'duration'] + C.CRUDE_FEATURES
    X = df[feats].to_numpy(float); y = df['target'].to_numpy(float)
    Xs = StandardScaler().fit_transform(X)
    gb = GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42)

    # grouped, leave-HX-out CV (ข้อ 3): the OLD KFold(shuffle=True) let a single HX's runs span
    # both train and test folds -- classic group leakage, since a fold could learn "this IS
    # E113A's typical rate" from other E113A runs in the training split. leave_run_out_cv
    # already generalizes to arbitrary `groups` (its GroupKFold call, not run-specific despite
    # the name), so passing HX as the group is a direct reuse, not a new implementation.
    groups = df['HX'].to_numpy()
    cv_gb = leave_run_out_cv(Xs, y, groups, gb, n_splits=min(C.DRIVER_CV_FOLDS, len(set(groups))))
    # naive baseline (ข้อ 3): predict the training folds' constant mean rate -- a real driver
    # model must beat "just guess the average fouling rate of the other HX" to be worth showing.
    cv_baseline = leave_run_out_cv(Xs, y, groups, DummyRegressor(strategy='mean'),
                                   n_splits=min(C.DRIVER_CV_FOLDS, len(set(groups))), scale=False)
    cv_r2_mean_grouped = cv_gb.get('r2_mean')
    baseline_r2_mean = cv_baseline.get('r2_mean')
    show_in_dashboard = bool(cv_r2_mean_grouped is not None and baseline_r2_mean is not None
                             and cv_r2_mean_grouped > baseline_r2_mean)
    gb.fit(Xs, y)
    # SHAP importance + direction
    try:
        import shap
        sv = shap.TreeExplainer(gb).shap_values(Xs)
        imp = np.abs(sv).mean(0)
        # direction: sign of correlation between feature and its shap
        direction = [float(np.sign(np.corrcoef(Xs[:, i], sv[:, i])[0, 1])) for i in range(len(feats))]
    except Exception:
        imp = gb.feature_importances_
        direction = [float(np.sign(np.corrcoef(Xs[:, i], y)[0, 1])) for i in range(len(feats))]
    order = np.argsort(imp)[::-1]
    label = {'film_temp': 'อุณหภูมิผิว (film)', 'flow': 'อัตราการไหล (velocity)', 'duration': 'อายุการเดินเครื่อง',
             'API': 'API crude', 'Asphaltenes_pct': 'Asphaltenes %', 'MCRT_pct': 'MCRT %', 'Visc_100C_cSt': 'ความหนืด 100°C'}
    drivers = [dict(feature=feats[i], label=label.get(feats[i], feats[i]),
                    importance=round(float(imp[i]), 5), direction=int(direction[i])) for i in order]
    # actionable levers from top controllable drivers
    levers = []
    for dvr in drivers[:4]:
        if dvr['feature'] in ('film_temp', 'flow') and dvr['importance'] > 0:
            act = 'ลด' if dvr['direction'] > 0 else 'เพิ่ม'
            levers.append(f"{act}{dvr['label']} → ลดอัตราการเกิดตะกรัน (driver อันดับต้น ๆ, ควบคุมได้)")
    return dict(target=C.DRIVER_TARGET, n=int(len(df)), cv_method='leave_hx_out',
                cv_r2_mean=cv_r2_mean_grouped, cv_r2_sd=cv_gb.get('r2_sd'),
                baseline_r2_mean=baseline_r2_mean, show_in_dashboard=show_in_dashboard,
                drivers=drivers, levers=levers,
                note='n=%d runs · leave-HX-out CV (was leaky within-HX KFold before 2026-07-20) · '
                     'R2 may be low/negative with few HX -- shown only if it beats the constant-mean '
                     'baseline (show_in_dashboard) · associative, not causation' % len(df))


def main():
    print('PHM analysis...')
    c1 = run_c1(); (DASH / 'propagation_models.json').write_text(json.dumps(c1, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'  C1 propagation: {len(c1["per_hx"])} HX, best overall = {c1["best_overall_model"]}, backtest={c1["backtest_rmse_days"]}')
    c2 = run_c2(); (DASH / 'rul.json').write_text(json.dumps(c2, ensure_ascii=False, indent=1), encoding='utf-8')
    atrisk = [h for h, v in c2.items() if v.get('prob_90', 0) >= 50]
    print(f'  C2 RUL: {len(c2)} HX, >=50% clean-prob within 90d: {atrisk}')
    c3 = run_c3(); (DASH / 'reliability.json').write_text(json.dumps(c3, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'  C3 reliability: pooled Weibull shape={c3["_pooled"]["shape"]} scale={c3["_pooled"]["scale"]} MTBC={c3["_pooled"]["mtbc"]}d')
    c4 = run_c4(); (DASH / 'drivers.json').write_text(json.dumps(c4, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'  C4 drivers: n={c4["n"]}, CV R2={c4["cv_r2_mean"]}±{c4["cv_r2_sd"]}, top={c4["drivers"][0]["label"]}')
    print('wrote propagation_models/rul/reliability/drivers .json')


if __name__ == '__main__':
    main()
