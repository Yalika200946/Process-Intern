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
from scipy.stats import weibull_min
from scipy.special import gamma as gammafn

REPO = Path(__file__).resolve().parent.parent
NB   = REPO / 'notebooks'
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
DASH = REPO / 'dashboard' / 'data'
sys.path.append(str(REPO))
from src.models import phm_config as C
from src.models.fouling_curves import MODELS_RISING as MODELS, fit_model, predict_cross

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

# ---------------- C1: per-HX model comparison + backtest ----------------
def run_c1():
    out = {}
    backtest = {m: [] for m in MODELS}
    for hx in HXES:
        d = dev[(dev.HX == hx)].dropna(subset=['run_id'])
        if d.empty:
            continue
        runs = d['run_id'].unique()
        cur_run = runs[-1]
        cur = d[d.run_id == cur_run].sort_values('days_on_duty')
        t = cur['days_on_duty'].to_numpy(float); y = cur['deviation'].to_numpy(float)
        thr = float(ttc.loc[hx, 'threshold']) if hx in ttc.index else float(np.nanmax(y) * 1.1)
        fits = [fit_model(m, t, y) for m in MODELS if len(t) >= 4]
        fits = [f for f in fits if f]
        best = min(fits, key=lambda f: f['aic']) if fits else None
        # backtest on COMPLETED runs (all but current): fit first 60%, predict time to run's final dev
        for r in runs[:-1]:
            rr = d[d.run_id == r].sort_values('days_on_duty')
            tt = rr['days_on_duty'].to_numpy(float); yy = rr['deviation'].to_numpy(float)
            if len(tt) < C.MIN_RUN_PTS:
                continue
            cut = int(len(tt) * C.BACKTEST_FRACTION)
            if cut < 4:
                continue
            dev_end = float(yy[-1]); actual_rem = float(tt[-1] - tt[cut-1])
            for m in MODELS:
                fm = fit_model(m, tt[:cut], yy[:cut])
                if not fm:
                    continue
                pr = predict_cross(m, fm['params'], tt[cut-1], dev_end)
                if pr is not None and actual_rem > 0:
                    backtest[m].append(abs(pr - actual_rem))
        # curve for display (downsampled) + best-model projection to threshold
        idx = np.linspace(0, len(t)-1, min(len(t), 40)).astype(int)
        proj_days = predict_cross(best['name'], best['params'], t[-1], thr) if best else None
        out[hx] = dict(
            n_runs=int(len(runs)), current_run_pts=int(len(t)),
            best_model=best['name'] if best else None,
            threshold=round(thr, 2), current_deviation=round(float(y[-1]), 2),
            models=[dict(name=f['name'], aic=round(f['aic'], 1), params=[round(p, 4) for p in f['params']]) for f in fits],
            curve=[dict(t=round(float(t[i]), 1), y=round(float(y[i]), 2)) for i in idx],
            best_proj_days=proj_days,
        )
    bt = {m: (round(float(np.mean(v)), 1) if v else None) for m, v in backtest.items()}
    bt_n = {m: len(v) for m, v in backtest.items()}
    best_overall = min([m for m in bt if bt[m] is not None], key=lambda m: bt[m], default=None)
    return dict(per_hx=out, backtest_rmse_days=bt, backtest_n=bt_n, best_overall_model=best_overall,
                note='backtest = fit first 60% of each completed run, predict time to its final deviation (out-of-sample RUL error, days)')

# ---------------- C2: Monte-Carlo RUL ----------------
def rate_rel_sd(hx):
    sub = fr[fr.HX == hx]['dRf_per_day'].dropna()
    if len(sub) >= 2 and sub.mean() != 0:
        return float(min(abs(sub.std() / sub.mean()), 1.5))
    return C.RATE_REL_SD_FALLBACK

def run_c2():
    out = {}
    for hx in HXES:
        if hx not in ttc.index:
            continue
        row = ttc.loc[hx]
        cur = float(row['current_deviation']); thr = float(row['threshold']); rate = float(row['rate_kW_per_day'])
        if cur >= thr:
            out[hx] = dict(past_threshold=True, p10=0, p50=0, p90=0,
                           **{f'prob_{h}': 100.0 for h in C.HORIZONS},
                           current_deviation=round(cur, 2), threshold=round(thr, 2))
            continue
        gap = thr - cur
        rsd = rate_rel_sd(hx)
        if rate <= 0:
            out[hx] = dict(past_threshold=False, p10=None, p50=None, p90=None,
                           **{f'prob_{h}': 0.0 for h in C.HORIZONS}, stable=True,
                           current_deviation=round(cur, 2), threshold=round(thr, 2), rate=round(rate, 4))
            continue
        samp_rate = rng.normal(rate, max(rsd * rate, 1e-6), C.MC_ITERS)
        samp_rate = np.clip(samp_rate, rate * 0.05, None)
        rul = gap / samp_rate
        p10, p50, p90 = np.percentile(rul, [10, 50, 90])
        out[hx] = dict(past_threshold=False,
                       p10=round(float(p10), 1), p50=round(float(p50), 1), p90=round(float(p90), 1),
                       **{f'prob_{h}': round(float((rul <= h).mean() * 100), 1) for h in C.HORIZONS},
                       current_deviation=round(cur, 2), threshold=round(thr, 2),
                       rate=round(rate, 4), rate_rel_sd=round(rsd, 3))
    return out

# ---------------- C3: Weibull survival / hazard ----------------
def run_c3():
    durs = fr[['HX', 'Duration_days']].dropna()
    pool = durs['Duration_days'].to_numpy(float)
    pool = pool[pool > 0]
    k_p, _, s_p = weibull_min.fit(pool, floc=0)
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
                           mtbc=round(s_p * gammafn(1 + 1 / k_p), 1), n=int(len(pool)))}
    for hx in HXES:
        sub = durs[durs.HX == hx]['Duration_days'].to_numpy(float); sub = sub[sub > 0]
        n = len(sub)
        if n >= C.WEIBULL_MIN_N:
            k, _, s = weibull_min.fit(sub, floc=0); conf = 'ok'
        elif n >= 1:
            k = k_p; s = sub.mean() / gammafn(1 + 1 / k); conf = 'low'   # pooled shape, per-HX scale
        else:
            k, s, conf = k_p, s_p, 'pooled'
        t0 = age.get(hx, 0.0)
        probs = {}
        R0 = surv(t0, k, s)
        for h in C.HORIZONS:
            probs[f'prob_{h}'] = round((1 - (surv(t0 + h, k, s) / R0 if R0 > 1e-9 else 0)) * 100, 1)
        ts = np.linspace(0, C.SURVIVAL_CURVE_DAYS, 60)
        curve = [dict(t=round(float(x), 0), R=round(surv(x, k, s), 4), hz=round(hazard(x, k, s) * 1000, 3)) for x in ts]
        out[hx] = dict(shape=round(k, 3), scale=round(s, 1), mtbc=round(s * gammafn(1 + 1 / k), 1),
                       n_runs=int(n), confidence=conf, days_on_duty=round(t0, 0),
                       hazard_now_per1000d=round(hazard(t0, k, s) * 1000, 3), **probs, curve=curve)
    return out

# ---------------- C4: degradation drivers ----------------
def run_c4():
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import cross_val_score, KFold
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
    cv = cross_val_score(gb, Xs, y, cv=KFold(C.DRIVER_CV_FOLDS, shuffle=True, random_state=42), scoring='r2')
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
    return dict(target=C.DRIVER_TARGET, n=int(len(df)),
                cv_r2_mean=round(float(cv.mean()), 3), cv_r2_sd=round(float(cv.std()), 3),
                drivers=drivers, levers=levers,
                note='n=%d runs · CV R2 อาจต่ำเพราะตัวอย่างน้อย · เป็นความสัมพันธ์ (associative) ไม่ใช่ causation' % len(df))


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
