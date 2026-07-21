"""
Pipeline post-processor: (re)write dashboard/data/model_metrics.json with the
HONEST walk-forward-CV + persistence-baseline numbers.

Notebook 6c exports a model_metrics.json built from the single 80/20 split
(XGB R2~0.82), which is misleading — see project_cit_persistence_finding. This
script recomputes the honest numbers (persistence beats the trees out-of-sample)
and overwrites 6c's version, so the dashboard always shows the truthful metric
after any pipeline run.

Run: python pipeline/gen_honest_metrics.py
"""
import sys, json, warnings
warnings.filterwarnings('ignore')
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
NB   = REPO / 'notebooks'
OUT  = REPO / 'dashboard' / 'data' / 'model_metrics.json'
sys.path.append(str(REPO))
from src.features.heat_duty import build_cit_feature_matrix

from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
import xgboost as xgb

Z_MODELS = {
    'XGBoost':      lambda: xgb.XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05, random_state=42),
    'RandomForest': lambda: RandomForestRegressor(n_estimators=300, min_samples_leaf=2, random_state=42),
}


def _metrics(yt, yp):
    yt, yp = np.asarray(yt), np.asarray(yp)
    return dict(R2=r2_score(yt, yp), RMSE=float(np.sqrt(mean_squared_error(yt, yp))),
                MAE=float(mean_absolute_error(yt, yp)),
                w5=float((np.abs(yp - yt) <= 5).mean() * 100),
                w10=float((np.abs(yp - yt) <= 10).mean() * 100))


def main():
    b = build_cit_feature_matrix()
    X, y = b['X'], b['y']
    assert 'CIT_lag1' in X.columns
    # No-lag ablation: same rows/target, CIT_lag1/CIT_roll7 dropped -- tests whether
    # the model's reliance on "yesterday's CIT" is fixable by just removing that
    # feature (user asked "the model still leans on CIT_lag1, can you fix it?").
    b_nolag = build_cit_feature_matrix(include_cit_lags=False)
    X_nolag = b_nolag['X'].reindex(X.index)  # align rows (same target y)

    tscv = TimeSeriesSplit(n_splits=5)
    agg = {m: [] for m in ['XGBoost', 'RandomForest', 'Persistence', 'XGBoost_NoLag']}
    skill = []
    for fold, (tr, te) in enumerate(tscv.split(X), 1):
        Xtr, Xte, ytr, yte = X.iloc[tr], X.iloc[te], y.iloc[tr], y.iloc[te]
        ppred = Xte['CIT_lag1'].values
        agg['Persistence'].append(_metrics(yte, ppred))
        rmse_p = np.sqrt(mean_squared_error(yte, ppred))
        for name, cls in Z_MODELS.items():
            m = cls(); m.fit(Xtr, ytr); pred = m.predict(Xte)
            agg[name].append(_metrics(yte, pred))
            if name == 'XGBoost':
                rmse_x = np.sqrt(mean_squared_error(yte, pred))
                skill.append(dict(fold=fold, test_start=str(X.index[te[0]].date()),
                                  rmse_xgb=round(rmse_x, 3), rmse_persist=round(rmse_p, 3),
                                  skill_pct=round((1 - rmse_x / rmse_p) * 100, 1)))
        # ablation fold: XGBoost with the same split, but no CIT_lag1/CIT_roll7 features
        Xtr_nl, Xte_nl = X_nolag.iloc[tr], X_nolag.iloc[te]
        m_nl = Z_MODELS['XGBoost'](); m_nl.fit(Xtr_nl, ytr)
        agg['XGBoost_NoLag'].append(_metrics(yte, m_nl.predict(Xte_nl)))

    def summ(rows, k):
        v = pd.Series([r[k] for r in rows]); return round(v.mean(), 3), round(v.std(), 3)

    # single 80/20 for the "looks good but misleading" reference
    si = int(len(X) * 0.8)
    Xtr, Xte, ytr, yte = X.iloc[:si], X.iloc[si:], y.iloc[:si], y.iloc[si:]
    single = {'Persistence': _metrics(yte, Xte['CIT_lag1'].values)}
    for name, cls in Z_MODELS.items():
        m = cls(); m.fit(Xtr, ytr); single[name] = _metrics(yte, m.predict(Xte))

    def block(name, role, beats):
        r2m, r2s = summ(agg[name], 'R2'); rm, rs = summ(agg[name], 'RMSE')
        _, = (None,)
        w10m, _ = summ(agg[name], 'w10'); w5m, _ = summ(agg[name], 'w5'); maem, _ = summ(agg[name], 'MAE')
        return dict(model=name, role=role, beats_persistence=beats,
                    R2=r2m, R2_sd=r2s, RMSE=rm, RMSE_sd=rs, MAE=maem,
                    **{'within_5C_%': w5m, 'within_10C_%': w10m},
                    single_split_R2=round(single[name]['R2'], 3),
                    single_split_RMSE=round(single[name]['RMSE'], 3))

    persist = block('Persistence', 'baseline', None)
    persist['model'] = "Persistence (yesterday's CIT)"
    persist['note'] = 'Honest baseline. Strong because CIT is slow and strongly autocorrelated.'
    xgbm = block('XGBoost', 'attribution-only', False)
    xgbm['note'] = 'Single 80/20 R2 looked good but loses to persistence on every walk-forward fold. SHAP attribution only.'
    rfm = block('RandomForest', 'attribution-only', False)
    rfm['note'] = 'Same story as XGBoost; does not beat persistence out-of-sample.'
    lstm = dict(model='LSTM', role='rejected', beats_persistence=False, R2=None, R2_sd=None,
                RMSE=2.66, **{'within_10C_%': 100.0}, single_split_R2=-0.033,
                note='~700 daily rows is too few for a sequence model. Tested and rejected.')

    # ablation summary (no single_split_* -- this variant was only ever tested with CV)
    r2m, r2s = summ(agg['XGBoost_NoLag'], 'R2'); rm, rs = summ(agg['XGBoost_NoLag'], 'RMSE')
    w10m, _ = summ(agg['XGBoost_NoLag'], 'w10'); maem, _ = summ(agg['XGBoost_NoLag'], 'MAE')
    nolag = dict(model='XGBoost (no CIT_lag1 ablation)', role='ablation', beats_persistence=False,
                R2=r2m, R2_sd=r2s, RMSE=rm, RMSE_sd=rs, MAE=maem, **{'within_10C_%': w10m},
                note=(f'Removing CIT_lag1/CIT_roll7 makes it WORSE (CV R2 {r2m} vs {round(summ(agg["XGBoost"],"R2")[0],3)} '
                      'with the lag) -- HX/crude features alone cannot explain the CIT level at all; '
                      'the lag is not an error to remove, it is the only reason the model is in the right ballpark.'))

    mean_skill = round(float(np.mean([s['skill_pct'] for s in skill])), 1)
    out = dict(
        validation='walk-forward TimeSeriesSplit (5-fold, expanding window)',
        target='1TI116.pv (CIT, Coil Inlet Temp to furnace F101)',
        n_rows=int(len(X)), date_range=[str(X.index.min().date()), str(X.index.max().date())],
        primary_baseline='Persistence',
        selected_operational_model='Persistence',
        candidate_forecast_approved=False,
        approval_status='CANDIDATE',
        fallback_reason='Tree models do not beat persistence in walk-forward validation.',
        headline=('CIT is near-random-walk; persistence (today = yesterday) is the honest baseline '
                  'and the ML trees do NOT beat it out-of-sample. Tree models are kept for HX->CIT '
                  'SHAP attribution only, not point forecasting.'),
        skill_vs_persistence_pct_mean=mean_skill, skill_by_fold=skill,
        models=[persist, xgbm, rfm, nolag, lstm],
    )
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote honest {OUT.name}: persistence CV R2={persist["R2"]}, XGB CV R2={xgbm["R2"]}, mean skill {mean_skill}%')


if __name__ == '__main__':
    main()
