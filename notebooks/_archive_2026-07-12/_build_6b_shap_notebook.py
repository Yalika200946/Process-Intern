"""
Helper script: builds 6b_shap_importance_ranking.ipynb from cell definitions.
Run once: python _build_6b_shap_notebook.py
Requires 6a_model_benchmark_xgb_lstm_rf.ipynb to have been run first (loads its
saved model artifacts from models/).
"""
import json
from pathlib import Path


def code_cell(source):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.strip().splitlines(keepends=True)
    }


def md_cell(source):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.strip().splitlines(keepends=True)
    }


cells = []

cells.append(md_cell("""
# SHAP Importance Ranking — Which HX Drives CIT Most

Replaces the raw `feature_importances_`-based `cit_model_importance` column in
`outputs/hx_Q_cleaning_priority.csv` with a **SHAP**-based importance, using the
XGBoost/RandomForest models trained and saved by `6a_model_benchmark_xgb_lstm_rf.ipynb`.

**Why XGBoost as the primary SHAP target:** `shap.TreeExplainer` is exact and fast
for tree ensembles. RandomForest is explained too as a cross-check that the ranking
isn't an XGBoost-specific artifact. LSTM is *not* explained with SHAP DeepExplainer
(known TF2/Keras3 compatibility issues, and unnecessary here — SHAP's role is
explaining the tree-based champion for the HX ranking); instead LSTM gets a
permutation-importance sanity check.

Sections:
1. Load feature matrix + saved model artifacts from `6a`
2. SHAP values — XGBoost (primary)
3. SHAP values — RandomForest (cross-check)
4. Per-HX aggregated SHAP importance + ranking plot
5. LSTM permutation importance (sanity check, not SHAP)
6. Rebuild `hx_Q_cleaning_priority_v2.csv` with SHAP-based `priority_score`
"""))

cells.append(md_cell("## 0. Imports & Load Artifacts"))

cells.append(code_cell("""
import warnings, os, sys
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import joblib
import shap
from pathlib import Path
from sklearn.metrics import mean_absolute_error

sys.path.append(str(Path.cwd()))
from cpht_features import build_cit_feature_matrix, HX_CONFIG

plt.rcParams.update({'figure.dpi': 110, 'font.size': 10,
                     'axes.grid': True, 'grid.alpha': 0.3})

REPO_ROOT  = Path(r'C:\\Desktop\\Bangchak Internship 2026\\furnace-optimization')
FIG_DIR    = REPO_ROOT / 'figures' / 'shap'
OUT_DIR    = REPO_ROOT / 'outputs'
MODELS_DIR = REPO_ROOT / 'models'
FIG_DIR.mkdir(parents=True, exist_ok=True)

xgb_model = joblib.load(MODELS_DIR / 'xgb_cit_model.joblib')
rf_model  = joblib.load(MODELS_DIR / 'rf_cit_model.joblib')
lstm_bundle = joblib.load(MODELS_DIR / 'lstm_scalers.joblib')
sx, sy, ENROL = lstm_bundle['scaler_X'], lstm_bundle['scaler_y'], lstm_bundle['enrol_window']

from tensorflow import keras
lstm_model = keras.models.load_model(MODELS_DIR / 'lstm_cit_model.keras')

print('Loaded XGBoost, RandomForest, and LSTM artifacts from', MODELS_DIR)
"""))

cells.append(code_cell("""
bundle = build_cit_feature_matrix()
X, y = bundle['X'], bundle['y']

# Same chronological 80/20 split as 6a — must match exactly for the loaded
# models' test set to be meaningful.
split_idx = int(len(X) * 0.8)
X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

print(f'Test set: {X_test.index.min().date()} -> {X_test.index.max().date()}  (n={len(X_test)})')
"""))

cells.append(md_cell("""
---
## 1. SHAP Values — XGBoost (primary)
"""))

cells.append(code_cell("""
explainer_xgb = shap.TreeExplainer(xgb_model)
shap_values_xgb = explainer_xgb.shap_values(X_test)

shap.summary_plot(shap_values_xgb, X_test, show=False, max_display=15)
plt.title('SHAP Summary — XGBoost CIT model (top 15 features)')
plt.tight_layout()
plt.savefig(FIG_DIR / 'shap_summary_xgboost.png', dpi=110, bbox_inches='tight')
plt.show()
"""))

cells.append(md_cell("## 2. SHAP Values — RandomForest (cross-check)"))

cells.append(code_cell("""
explainer_rf = shap.TreeExplainer(rf_model)
shap_values_rf = explainer_rf.shap_values(X_test)

shap.summary_plot(shap_values_rf, X_test, show=False, max_display=15)
plt.title('SHAP Summary — RandomForest CIT model (top 15 features)')
plt.tight_layout()
plt.savefig(FIG_DIR / 'shap_summary_randomforest.png', dpi=110, bbox_inches='tight')
plt.show()
"""))

cells.append(md_cell("""
---
## 3. Per-HX Aggregated SHAP Importance

Per-HX importance = sum of `mean(|SHAP value|)` across that HX's engineered
feature columns (`_Q_norm`, `_dT_cold`, `_duty_kW`, `_dT_hot`) — mirrors the
aggregation pattern already used for `cit_model_importance` in
`5_HX_fouling_CIT_ranking.ipynb` section 10, just swapping the importance source.
"""))

cells.append(code_cell("""
def aggregate_shap_per_hx(shap_values, feature_names, hx_list):
    mean_abs_shap = pd.Series(np.abs(shap_values).mean(axis=0), index=feature_names)
    hx_importance = {}
    for hx in hx_list:
        cols = [c for c in feature_names if c.startswith(hx + '_')]
        if cols:
            hx_importance[hx] = mean_abs_shap[cols].sum()
    return pd.Series(hx_importance).sort_values(ascending=False)

hx_list = list(HX_CONFIG.keys())
shap_hx_xgb = aggregate_shap_per_hx(shap_values_xgb, X.columns, hx_list)
shap_hx_rf  = aggregate_shap_per_hx(shap_values_rf,  X.columns, hx_list)

comparison = pd.DataFrame({'XGBoost_SHAP': shap_hx_xgb, 'RandomForest_SHAP': shap_hx_rf}).fillna(0)
comparison['rank_corr'] = comparison['XGBoost_SHAP'].rank().corr(comparison['RandomForest_SHAP'].rank())
print(f\"XGBoost vs RandomForest per-HX SHAP ranking Spearman-like agreement: \"\n      f\"{comparison['XGBoost_SHAP'].rank().corr(comparison['RandomForest_SHAP'].rank(), method='spearman'):.3f}\")
comparison.sort_values('XGBoost_SHAP', ascending=False).round(4)
"""))

cells.append(code_cell("""
fig, ax = plt.subplots(figsize=(9, 6))
order = shap_hx_xgb.sort_values(ascending=True).index
ax.barh(order, shap_hx_xgb.loc[order], color='tab:purple')
ax.set_xlabel('Aggregated |SHAP value| (XGBoost, Q-based features)')
ax.set_title('HX Importance to CIT — SHAP-based (XGBoost)')
plt.tight_layout()
plt.savefig(FIG_DIR / 'shap_hx_importance_ranking.png', dpi=110, bbox_inches='tight')
plt.show()

shap_hx_xgb.sort_values(ascending=False)
"""))

cells.append(md_cell("""
---
## 4. LSTM Permutation Importance (sanity check)

Not SHAP (DeepExplainer has known TF2/Keras3 compatibility issues and isn't
needed here — LSTM's role in the benchmark is to confirm a sequence model
doesn't beat the tree-based champion, not to drive the HX ranking). Instead:
shuffle each feature across the windowed test set and measure the increase in
MAE — a model-agnostic importance measure that works for any architecture.
"""))

cells.append(code_cell("""
Xte_s = sx.transform(X_test)
yte_s = sy.transform(y_test.values.reshape(-1, 1)).flatten()

def make_windows(arr, tgt, window):
    Xw, yw = [], []
    for i in range(window, len(arr)):
        Xw.append(arr[i - window:i])
        yw.append(tgt[i])
    return np.array(Xw), np.array(yw)

Xte_w, yte_w = make_windows(Xte_s, yte_s, ENROL)

baseline_pred = lstm_model.predict(Xte_w, verbose=0).flatten()
baseline_mae  = mean_absolute_error(yte_w, baseline_pred)

rng = np.random.default_rng(42)
perm_importance = {}
for j, feat_name in enumerate(X.columns):
    Xte_perm = Xte_w.copy()
    perm_idx = rng.permutation(Xte_perm.shape[0])
    Xte_perm[:, :, j] = Xte_perm[perm_idx, :, j]
    pred_perm = lstm_model.predict(Xte_perm, verbose=0).flatten()
    perm_importance[feat_name] = mean_absolute_error(yte_w, pred_perm) - baseline_mae

perm_importance_s = pd.Series(perm_importance).clip(lower=0)

lstm_hx_importance = {}
for hx in hx_list:
    cols = [c for c in X.columns if c.startswith(hx + '_')]
    if cols:
        lstm_hx_importance[hx] = perm_importance_s[cols].sum()
lstm_hx_importance_s = pd.Series(lstm_hx_importance).sort_values(ascending=False)

print(f'Baseline LSTM test MAE: {baseline_mae:.3f} °C')
lstm_hx_importance_s.round(4)
"""))

cells.append(code_cell("""
rank_compare = pd.DataFrame({
    'XGBoost_SHAP_rank'      : shap_hx_xgb.rank(ascending=False),
    'LSTM_permutation_rank'  : lstm_hx_importance_s.reindex(shap_hx_xgb.index).rank(ascending=False),
}).sort_values('XGBoost_SHAP_rank')
agreement = rank_compare['XGBoost_SHAP_rank'].corr(rank_compare['LSTM_permutation_rank'], method='spearman')
print(f'XGBoost-SHAP vs LSTM-permutation rank agreement (Spearman): {agreement:.3f}')
rank_compare
"""))

cells.append(md_cell("""
---
## 5. Rebuild Cleaning-Priority Table with SHAP-Based Importance

Loads the existing `outputs/hx_Q_cleaning_priority.csv` (built in
`5_HX_fouling_CIT_ranking.ipynb`) and replaces `cit_model_importance` with the
SHAP-based `cit_shap_importance`, then recomputes `priority_score` with the
same equal-weight min-max formula:

`priority_score = (minmax(fouling_rate_abs) + minmax(cit_shap_importance) + minmax(Q_CIT_correlation)) / 3`

Only the importance source changes — `Q_fouling_rate_abs`, `Q_CIT_correlation`,
`recommended_action`, and `Q_drop_%` are reused as-is (already validated,
per the project's decision not to re-derive cleaning-event detection).
"""))

cells.append(code_cell("""
def minmax(s):
    return (s - s.min()) / (s.max() - s.min()) if s.max() > s.min() else pd.Series(0, index=s.index)

priority_v1 = pd.read_csv(OUT_DIR / 'hx_Q_cleaning_priority.csv', index_col=0)
print('Loaded existing priority table:', priority_v1.shape)

hx_index = priority_v1.index
cit_shap_importance = shap_hx_xgb.reindex(hx_index).fillna(0)

fr_abs = priority_v1['Q_fouling_rate_abs']
qcit   = priority_v1['Q_CIT_correlation']

priority_score_v2 = (minmax(fr_abs) + minmax(cit_shap_importance) + minmax(qcit)) / 3

priority_v2 = priority_v1.copy()
priority_v2['cit_shap_importance'] = cit_shap_importance
priority_v2 = priority_v2.drop(columns=['cit_model_importance'])
priority_v2['priority_score'] = priority_score_v2
priority_v2 = priority_v2[['Q_fouling_rate_abs', 'cit_shap_importance', 'Q_CIT_correlation',
                            'priority_score', 'expected_CIT_gain_C', 'recommended_action', 'Q_drop_%']]
priority_v2 = priority_v2.sort_values('priority_score', ascending=False)

out_path = OUT_DIR / 'hx_Q_cleaning_priority_v2.csv'
priority_v2.to_csv(out_path)
print(f'Saved -> {out_path}')
priority_v2.round(4)
"""))

cells.append(code_cell("""
fig, ax = plt.subplots(figsize=(9, 6))
order = priority_v2.sort_values('priority_score').index
ax.barh(order, priority_v2.loc[order, 'priority_score'], color='tab:red')
ax.set_xlabel('SHAP-based combined priority score (0-1)')
ax.set_title('HX Cleaning Priority — SHAP-based Importance\\n(Q fouling rate + SHAP CIT importance + Q-CIT corr)')
plt.tight_layout()
plt.savefig(FIG_DIR / 'hx_cleaning_priority_shap.png', dpi=110, bbox_inches='tight')
plt.show()
"""))

cells.append(code_cell("""
rank_shift = pd.DataFrame({
    'v1_rank (feature_importances_)': priority_v1['priority_score'].rank(ascending=False).astype(int),
    'v2_rank (SHAP)'                : priority_v2['priority_score'].rank(ascending=False).astype(int),
}).sort_values('v2_rank (SHAP)')
rank_shift['rank_change'] = rank_shift['v1_rank (feature_importances_)'] - rank_shift['v2_rank (SHAP)']
print('Ranking sanity check — SHAP-based ranking vs the previous feature_importances_-based ranking:')
rank_shift
"""))

cells.append(md_cell("""
---
## Summary

- `outputs/hx_Q_cleaning_priority_v2.csv` now ranks HX by a **SHAP-based**
  `cit_shap_importance` instead of raw `feature_importances_`.
- Cross-checked against RandomForest SHAP and LSTM permutation importance —
  see the rank-agreement figures above for how stable the ranking is across
  model choice.
- `6c_six_month_forecast_and_dashboard_export.ipynb` consumes this v2 file to
  build the final cleaning-recommendation table and dashboard export.
"""))

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.x"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out_path = Path(__file__).parent / "6b_shap_importance_ranking.ipynb"
out_path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {out_path}")
