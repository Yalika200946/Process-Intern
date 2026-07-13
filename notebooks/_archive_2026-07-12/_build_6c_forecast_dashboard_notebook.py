"""
Helper script: builds 6c_six_month_forecast_and_dashboard_export.ipynb from cell definitions.
Run once: python _build_6c_forecast_dashboard_notebook.py
Requires 6a and 6b to have been run first (Model_Comparison_Metrics.csv,
hx_Q_cleaning_priority_v2.csv must exist in outputs/).
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
# Six-Month Forecast & Dashboard Export

Answers the project's core question directly: **which HX should be cleaned, and
when** — by linearly extrapolating each HX's fouling-deviation signal 182 days
(~6 months) forward from `Data/Time_To_Clean_Prediction.csv`, then exporting
everything the static HTML dashboard needs as JSON.

**No new detection/threshold logic is introduced here** — `Time_To_Clean_Prediction.csv`
(built in `3b_time_to_clean_prediction.ipynb`) already contains a validated
per-HX deviation, threshold, and fouling rate; this notebook only projects that
trend forward and packages the result for the dashboard.

Sections:
1. Load `Time_To_Clean_Prediction.csv`, `hx_Q_cleaning_priority_v2.csv` (from `6b`),
   `Model_Comparison_Metrics.csv` (from `6a`)
2. 182-day linear extrapolation per HX
3. Final cleaning-recommendation table (HX, priority rank, projected trigger date)
4. Plot: 6-month forecast for top-priority HX
5. Export `dashboard/data/*.json`
"""))

cells.append(md_cell("## 0. Imports & Configuration"))

cells.append(code_cell("""
import json as jsonlib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

plt.rcParams.update({'figure.dpi': 110, 'font.size': 10,
                     'axes.grid': True, 'grid.alpha': 0.3})

DATA_DIR      = Path(r'C:\\Desktop\\Bangchak Internship 2026\\Data')
REPO_ROOT     = Path(r'C:\\Desktop\\Bangchak Internship 2026\\furnace-optimization')
OUT_DIR       = REPO_ROOT / 'outputs'
FIG_DIR       = REPO_ROOT / 'figures' / 'forecast_6mo'
DASHBOARD_DIR = REPO_ROOT / 'dashboard' / 'data'
FIG_DIR.mkdir(parents=True, exist_ok=True)
DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

HORIZON_DAYS = 182   # ~6 months look-ahead
"""))

cells.append(md_cell("""
---
## 1. Load Inputs
"""))

cells.append(code_cell("""
ttc = pd.read_csv(DATA_DIR / 'Time_To_Clean_Prediction.csv')
priority_v2 = pd.read_csv(OUT_DIR / 'hx_Q_cleaning_priority_v2.csv', index_col=0)
model_metrics = pd.read_csv(OUT_DIR / 'Model_Comparison_Metrics.csv')

# Reference 'as of' date -- last timestamp in the underlying process data, same
# basis Time_To_Clean_Prediction.csv itself was built from.
last_date = pd.read_csv(DATA_DIR / 'Process_information_cleaned.csv',
                         index_col='Timestamp', parse_dates=True).index.max()

print(f'Time_To_Clean_Prediction.csv: {ttc.shape[0]} HX rows')
print(f'hx_Q_cleaning_priority_v2.csv: {priority_v2.shape[0]} HX rows')
print(f'As-of date: {last_date.date()}')
ttc.head()
"""))

cells.append(md_cell("""
---
## 2. 182-Day Linear Extrapolation per HX

`projected_deviation(t) = current_deviation + rate_degC_per_day * t`

Only HX with a **positive** fouling rate (deviation growing) can cross their
threshold going forward; HX with a flat/negative rate are marked
`beyond_horizon` (consistent with the convention already used in
`Time_To_Clean_Prediction.csv` / `3b_time_to_clean_prediction.ipynb`).
"""))

cells.append(code_cell("""
forecast_rows = []
forecast_series = {}

for _, row in ttc.iterrows():
    hx = row['HX']
    current_dev = row['current_deviation']
    threshold   = row['threshold']
    rate        = row['rate_degC_per_day']

    days = np.arange(0, HORIZON_DAYS + 1)
    dates = [last_date + pd.Timedelta(days=int(d)) for d in days]
    projected = current_dev + rate * days

    if current_dev >= threshold:
        # Already past trigger as of the as-of date -- due now, not a future projection.
        days_to_cross = 0.0
    elif rate > 0:
        days_to_cross = (threshold - current_dev) / rate
    else:
        days_to_cross = np.nan

    if pd.notna(days_to_cross) and 0 <= days_to_cross <= HORIZON_DAYS:
        trigger_date = last_date + pd.Timedelta(days=float(days_to_cross))
        within_horizon = True
    else:
        trigger_date = pd.NaT
        within_horizon = False

    forecast_series[hx] = {
        'dates': [d.strftime('%Y-%m-%d') for d in dates],
        'projected_deviation': [round(float(v), 3) for v in projected],
        'threshold': float(threshold),
        'current_deviation': float(current_dev),
    }

    forecast_rows.append({
        'HX'                  : hx,
        'effort_tier'         : row['effort_tier'],
        'current_deviation'   : round(current_dev, 3),
        'threshold'           : round(threshold, 3),
        'rate_degC_per_day'   : round(rate, 5),
        'days_to_threshold_6mo': round(days_to_cross, 1) if pd.notna(days_to_cross) else np.nan,
        'projected_clean_date': trigger_date.date().isoformat() if within_horizon else None,
        'at_risk_within_6mo'  : bool(within_horizon or row['days_to_threshold'] == 0),
    })

forecast_df = pd.DataFrame(forecast_rows).sort_values('days_to_threshold_6mo', na_position='last')
print(f'{int(forecast_df[\"at_risk_within_6mo\"].sum())} of {len(forecast_df)} HX projected to need cleaning within 6 months')
forecast_df
"""))

cells.append(md_cell("""
---
## 3. Final Cleaning-Recommendation Table

Combines the SHAP-based priority ranking (`6b`) with the 6-month forecast
(section 2) — this is the direct answer to "which HX, and when."
"""))

cells.append(code_cell("""
recommendation = priority_v2[['priority_score', 'cit_shap_importance', 'Q_fouling_rate_abs',
                               'recommended_action']].copy()
recommendation['priority_rank'] = recommendation['priority_score'].rank(ascending=False).astype(int)

fc_indexed = forecast_df.set_index('HX')
recommendation = recommendation.join(
    fc_indexed[['effort_tier', 'projected_clean_date', 'at_risk_within_6mo', 'days_to_threshold_6mo']]
)
recommendation = recommendation.sort_values('priority_rank')

out_path = OUT_DIR / 'Cleaning_Recommendation_Final.csv'
recommendation.to_csv(out_path)
print(f'Saved -> {out_path}')
recommendation.round(3)
"""))

cells.append(code_cell("""
print('='*70)
print('FINAL CLEANING RECOMMENDATIONS (priority rank + 6-month forecast)')
print('='*70)
for hx, row in recommendation.head(8).iterrows():
    when = row['projected_clean_date'] if pd.notna(row['projected_clean_date']) else row['recommended_action']
    print(f\"  #{int(row['priority_rank'])}  {hx:<10}  priority={row['priority_score']:.3f}  \"
          f\"effort={row['effort_tier']:<26}  clean by: {when}\")
print('='*70)
"""))

cells.append(md_cell("""
---
## 4. Plot: 6-Month Forecast for Top-Priority HX
"""))

cells.append(code_cell("""
top5 = recommendation.head(5).index.tolist()

fig, ax = plt.subplots(figsize=(14, 6))
colors = plt.cm.tab10(np.linspace(0, 1, len(top5)))
for hx, color in zip(top5, colors):
    fc = forecast_series[hx]
    dates = pd.to_datetime(fc['dates'])
    ax.plot(dates, fc['projected_deviation'], lw=1.8, color=color, label=f'{hx}')
    ax.axhline(fc['threshold'], color=color, ls=':', lw=1, alpha=0.6)

ax.axvline(last_date, color='black', ls='--', lw=1, label='Today (as-of date)')
ax.set_ylabel('Projected fouling deviation')
ax.set_xlabel('Date')
ax.set_title('6-Month Fouling-Deviation Forecast — Top 5 Priority HX\\n(dotted line = each HX\\'s own cleaning threshold)')
ax.legend(ncol=3, fontsize=9)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
plt.tight_layout()
plt.savefig(FIG_DIR / 'six_month_forecast_top5.png', dpi=110, bbox_inches='tight')
plt.show()
"""))

cells.append(md_cell("""
---
## 5. Export Dashboard Data (`dashboard/data/*.json`)
"""))

cells.append(code_cell("""
# hx_ranking.json -- SHAP-based cleaning priority table
hx_ranking = priority_v2.reset_index().rename(columns={'index': 'HX'})
hx_ranking.columns = ['HX'] + list(hx_ranking.columns[1:])
hx_ranking_records = jsonlib.loads(hx_ranking.round(4).to_json(orient='records'))
with open(DASHBOARD_DIR / 'hx_ranking.json', 'w') as f:
    jsonlib.dump(hx_ranking_records, f, indent=2)

# forecast_6mo.json -- per-HX daily projected series
with open(DASHBOARD_DIR / 'forecast_6mo.json', 'w') as f:
    jsonlib.dump(forecast_series, f, indent=2)

# model_metrics.json -- XGBoost/RF/LSTM benchmark
model_metrics_records = jsonlib.loads(model_metrics.round(3).to_json(orient='records'))
with open(DASHBOARD_DIR / 'model_metrics.json', 'w') as f:
    jsonlib.dump(model_metrics_records, f, indent=2)

# cleaning_recommendations.json -- final synthesized table
reco_export = recommendation.reset_index().rename(columns={'index': 'HX'})
reco_records = jsonlib.loads(reco_export.round(4).to_json(orient='records'))
with open(DASHBOARD_DIR / 'cleaning_recommendations.json', 'w') as f:
    jsonlib.dump(reco_records, f, indent=2)

print('Exported dashboard data files:')
for f in sorted(DASHBOARD_DIR.glob('*.json')):
    print(' -', f.name, f'({f.stat().st_size:,} bytes)')
"""))

cells.append(code_cell("""
# Validate every exported file is well-formed JSON
for f in sorted(DASHBOARD_DIR.glob('*.json')):
    with open(f) as fh:
        obj = jsonlib.load(fh)
    n = len(obj) if isinstance(obj, list) else len(obj.keys())
    print(f'{f.name}: OK ({n} top-level entries)')
"""))

cells.append(md_cell("""
---
## Summary

- **6-month forecast**: linear extrapolation of each HX's validated fouling
  deviation rate against its own cleaning threshold, 182 days forward from the
  latest process data.
- **Final recommendation**: `outputs/Cleaning_Recommendation_Final.csv` merges
  SHAP-based priority rank (`6b`) with the projected cleaning date (this notebook)
  — this is the direct "which HX, and when" answer.
- **Dashboard data**: `dashboard/data/hx_ranking.json`, `forecast_6mo.json`,
  `model_metrics.json`, `cleaning_recommendations.json` — consumed by
  `dashboard/index.html`.
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

out_path = Path(__file__).parent / "6c_six_month_forecast_and_dashboard_export.ipynb"
out_path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {out_path}")
