"""
Build 3 verification/exploration notebooks from the .py scratch files,
splitting at logical section boundaries so each block of output can be
inspected on its own.

Run once:
    python _build_scratch_notebooks.py
"""
import json
from pathlib import Path

HERE = Path(__file__).parent


def code_cell(src):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": src.strip("\n").splitlines(keepends=True)}


def md_cell(src):
    return {"cell_type": "markdown", "metadata": {},
            "source": src.strip("\n").splitlines(keepends=True)}


def write_nb(cells, name):
    nb = {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.13.0"},
        },
        "cells": cells,
    }
    out = HERE / name
    with open(out, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
    print(f"wrote {out}  ({len(cells)} cells)")


SHARED_SETUP = r"""
import sys, os, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.getcwd())   # so `from hx_config import HX_CONFIG` works
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from hx_config import HX_CONFIG
print(f'{len(HX_CONFIG)} heat exchangers configured')
"""

LOAD_DATA = r"""
df = pd.read_csv(r'C:\Desktop\Bangchak Internship 2026\Data\Process_information_cleaned.csv',
                 index_col='Timestamp', parse_dates=True)
print('data shape:', df.shape)
print('date range:', df.index.min().date(), '->', df.index.max().date())
df.head(3)
"""

PHYSICS_CONST = r"""
CP_CRUDE = 2.2     # kJ/kg-K   (Equations_Reference doc, assumed crude property)
RHO_CRUDE = 850    # kg/m3     (assumed crude property)
"""

PARSE_TAGS = r"""
def classify_side(items):
    flow = t_in = t_out = None
    unclassified = []
    for tag, label, unit in items:
        ll = label.lower()
        if unit == 'M3/HR':
            flow = tag
        elif unit == 'DEGC':
            if 'inlet' in ll:
                t_in = tag
            elif 'outlet' in ll:
                t_out = tag
            else:
                unclassified.append(tag)
    # fallback: e.g. E113A hot side has 'Residue from Distillation' with no
    # explicit inlet/outlet wording -- treat the lone unclassified temp as inlet
    if t_in is None and unclassified:
        t_in = unclassified[0]
    return flow, t_in, t_out

def parse_hx(cfg):
    cold_flow, cold_in, cold_out = classify_side(cfg['cold'])
    hot_flow,  hot_in,  hot_out  = classify_side(cfg['hot'])
    return dict(cold_flow=cold_flow, cold_in=cold_in, cold_out=cold_out,
                hot_flow=hot_flow,   hot_in=hot_in,   hot_out=hot_out)

streams = {hx: parse_hx(cfg) for hx, cfg in HX_CONFIG.items()}
pd.DataFrame(streams).T
"""

# ============================================================================
# 1) test_features.ipynb  -- verify tag classification + feature engineering
# ============================================================================
cells = []
cells.append(md_cell(r"""
# Scratch 1 — Per-HX Feature Engineering Verification

ทดสอบว่า:
- ตัว parser ดึง `cold_flow / cold_in / cold_out / hot_flow / hot_in / hot_out`
  ออกจาก `HX_CONFIG` ได้ถูกทุกตัว
- มี tag ไหนใน config ที่ไม่อยู่ใน CSV หรือไม่
- คำนวณ `dT_cold / dT_hot / eps (effectiveness) / duty (kW)` ออกมาได้ค่าที่
  สมเหตุสมผล (eps ส่วนใหญ่ควรอยู่ระหว่าง 0–1)
- มี TAM gap กี่ช่องในข้อมูลที่ cleaning notebook ทิ้งไว้
"""))
cells.append(md_cell("## Setup"))
cells.append(code_cell(SHARED_SETUP))
cells.append(code_cell(LOAD_DATA))
cells.append(code_cell(PHYSICS_CONST))

cells.append(md_cell("## 1. Tag classification per HX"))
cells.append(code_cell(PARSE_TAGS))
cells.append(md_cell("### Check: every classified tag actually exists in the CSV"))
cells.append(code_cell(r"""
report = []
for hx, s in streams.items():
    missing = [k for k, v in s.items() if v is not None and v not in df.columns]
    report.append({'HX': hx, **s, 'missing_in_csv': ', '.join(missing) if missing else ''})
pd.DataFrame(report)
"""))

cells.append(md_cell(r"""
## 2. Compute per-HX features

- `dT_cold` = cold outlet − cold inlet   (degC gained by crude)
- `dT_hot`  = hot inlet − hot outlet     (degC given up by hot stream)
- `eps`     = (T_cold,out − T_cold,in) / (T_hot,in − T_cold,in)  — clipped to [-0.5, 1.5]
- `duty_kW` = ρ · V · cp · ΔT / 3600     — uses cold-side flow if available, else hot-side
"""))
cells.append(code_cell(r"""
feat = pd.DataFrame(index=df.index)
for hx, s in streams.items():
    if s['cold_in'] and s['cold_out']:
        feat[f'{hx}_dT_cold'] = df[s['cold_out']] - df[s['cold_in']]
    if s['hot_in'] and s['hot_out']:
        feat[f'{hx}_dT_hot']  = df[s['hot_in']]  - df[s['hot_out']]
    if s['cold_in'] and s['cold_out'] and s['hot_in']:
        denom = df[s['hot_in']] - df[s['cold_in']]
        eps_series = (df[s['cold_out']] - df[s['cold_in']]) / denom.replace(0, np.nan)
        feat[f'{hx}_eps'] = eps_series.clip(lower=-0.5, upper=1.5)
    if s['cold_flow'] and s['cold_in'] and s['cold_out']:
        feat[f'{hx}_duty_kW'] = RHO_CRUDE * df[s['cold_flow']] * CP_CRUDE * (df[s['cold_out']] - df[s['cold_in']]) / 3600
    elif s['hot_flow'] and s['hot_in'] and s['hot_out']:
        feat[f'{hx}_duty_kW'] = RHO_CRUDE * df[s['hot_flow']] * CP_CRUDE * (df[s['hot_in']] - df[s['hot_out']]) / 3600

print('feature matrix shape:', feat.shape)
feat.describe().T[['mean', 'std', 'min', 'max']].round(3)
"""))

cells.append(md_cell("### eps sanity (mostly should be in 0–1; out-of-range hints at sensor or wiring issue)"))
cells.append(code_cell(r"""
eps_cols = [c for c in feat.columns if c.endswith('_eps')]
feat[eps_cols].describe().T[['mean', 'std', 'min', 'max']].round(3)
"""))

cells.append(md_cell("### Quick visual: eps over time for all HX"))
cells.append(code_cell(r"""
fig, axes = plt.subplots(4, 4, figsize=(16, 10), sharex=True)
axes = axes.flatten()
for i, hx in enumerate(HX_CONFIG.keys()):
    col = f'{hx}_eps'
    ax = axes[i]
    if col in feat.columns:
        ax.plot(feat.index, feat[col], lw=0.5, color='tab:blue', alpha=0.7)
        ax.plot(feat.index, feat[col].rolling(14, min_periods=5).mean(), lw=1.4, color='tab:red')
    ax.set_title(hx, fontsize=9)
    ax.tick_params(axis='x', labelrotation=45, labelsize=7)
for j in range(len(HX_CONFIG), len(axes)):
    axes[j].set_visible(False)
fig.suptitle('eps per HX — blue=daily, red=14d rolling mean', y=1.01)
plt.tight_layout(); plt.show()
"""))

cells.append(md_cell("## 3. Date gaps (TAM segments inherited from cleaning step)"))
cells.append(code_cell(r"""
diffs = df.index.to_series().diff().dt.days
gaps = diffs[diffs > 1]
print(f'{len(gaps)} gap(s) > 1 day in the cleaned-CSV index:')
gaps
"""))

write_nb(cells, "test_features.ipynb")


# ============================================================================
# 2) test_fouling.ipynb  -- TAM segment + per-HX clean-event + fouling rate
# ============================================================================
cells = []
cells.append(md_cell(r"""
# Scratch 2 — Shutdown Segments, Clean-Event Inference & Fouling Rate Ranking

Logic ที่จะทดสอบ:
1. **Global TAM segments** — re-detect จาก gap ใน index ของ cleaned CSV
   (1_cleaning_data_process.ipynb ตัด shutdown ออกแล้วเลยเหลือ gap ทิ้งไว้)
2. **Per-HX local clean events** — ภายในแต่ละ segment ถ้า eps ของ HX นั้น
   กระโดดขึ้นเกิน 2.5σ ของการเปลี่ยนแปลงรายวัน → ถือว่ามีการ clean เกิดขึ้น
3. **Fouling rate** — fit slope ของ eps ต่อ day ในแต่ละ campaign แล้วเอา
   median ต่อ HX มา rank ว่าตัวไหน foul เร็วสุด
4. **Cleaning recommendation** — เอา trend ของ campaign ปัจจุบันมา project
   ไปข้างหน้าจน eps ลด > 10–15% (trigger จาก CPHT_Cleaning_and_Problem_Control_Plan.docx)
"""))

cells.append(md_cell("## Setup"))
cells.append(code_cell(SHARED_SETUP))
cells.append(code_cell(LOAD_DATA))
cells.append(code_cell(PHYSICS_CONST))
cells.append(code_cell(PARSE_TAGS))

cells.append(md_cell("## 1. Build eps (thermal effectiveness) per HX"))
cells.append(code_cell(r"""
eps = pd.DataFrame(index=df.index)
for hx, s in streams.items():
    if s['cold_in'] and s['cold_out'] and s['hot_in']:
        denom = (df[s['hot_in']] - df[s['cold_in']]).replace(0, np.nan)
        e = (df[s['cold_out']] - df[s['cold_in']]) / denom
        eps[hx] = e.clip(lower=-0.5, upper=1.5)
eps.describe().T[['mean', 'std', 'min', 'max']].round(3)
"""))

cells.append(md_cell("## 2. Global TAM segments (gap > 1 day in the cleaned-CSV index)"))
cells.append(code_cell(r"""
day_gap = df.index.to_series().diff().dt.days
seg_id = (day_gap > 1).cumsum()
segments = []
for _, idx in df.groupby(seg_id).groups.items():
    segments.append((idx.min(), idx.max()))

print(f'{len(segments)} global TAM segment(s):')
for s in segments:
    print(' ', s[0].date(), '->', s[1].date(), f'({(s[1]-s[0]).days} days)')
"""))

cells.append(md_cell(r"""
## 3. Per-HX local clean-event detection
ภายในแต่ละ TAM segment ใช้กฎ: smooth eps ด้วย rolling-7d → ดูค่า diff →
ถ้า diff > 2.5σ ของ diff นั้น ๆ ในช่วงเดียวกัน = สงสัย clean event
จากนั้นใช้จุดเหล่านี้แบ่งเป็น campaign ย่อย (ขั้นต่ำ 20 วันต่อ campaign).
"""))
cells.append(code_cell(r"""
MIN_CAMPAIGN_DAYS = 20

def detect_campaigns(series, seg_start, seg_end):
    s = series.loc[seg_start:seg_end].dropna()
    if len(s) < MIN_CAMPAIGN_DAYS:
        return [(seg_start, seg_end)]
    smooth = s.rolling(7, min_periods=3, center=False).mean()
    delta = smooth.diff()
    thresh = delta.std(skipna=True) * 2.5
    if not np.isfinite(thresh) or thresh <= 0:
        return [(seg_start, seg_end)]
    jump_days = sorted(delta.index[delta > thresh])
    boundaries, last = [seg_start], None
    for d in jump_days:
        if last is None or (d - last).days > 5:   # merge jumps within 5d
            boundaries.append(d)
        last = d
    boundaries.append(seg_end + pd.Timedelta(days=1))
    boundaries = sorted(set(boundaries))
    campaigns = []
    for i in range(len(boundaries) - 1):
        c_start, c_end = boundaries[i], boundaries[i + 1] - pd.Timedelta(days=1)
        if c_end < c_start:
            continue
        if (c_end - c_start).days + 1 >= MIN_CAMPAIGN_DAYS:
            campaigns.append((c_start, c_end))
    return campaigns if campaigns else [(seg_start, seg_end)]

all_campaigns = {}
for hx in eps.columns:
    camps = []
    for seg_start, seg_end in segments:
        camps.extend(detect_campaigns(eps[hx], seg_start, seg_end))
    all_campaigns[hx] = camps

print('Campaigns detected per HX:')
print(pd.Series({hx: len(c) for hx, c in all_campaigns.items()}).sort_values(ascending=False))
"""))

cells.append(md_cell("### Visualize campaigns for the HX with the most detected events"))
cells.append(code_cell(r"""
example_hx = max(all_campaigns, key=lambda k: len(all_campaigns[k]))
fig, ax = plt.subplots(figsize=(14, 4))
ax.plot(eps.index, eps[example_hx], lw=0.5, color='gray', alpha=0.6, label='daily eps')
ax.plot(eps.index, eps[example_hx].rolling(7, min_periods=3).mean(),
        lw=1.5, color='tab:blue', label='7-day rolling mean')
for c_start, c_end in all_campaigns[example_hx]:
    ax.axvline(c_start, color='tab:green', ls='--', lw=1, alpha=0.7)
ax.set_title(f'{example_hx}: detected cleaning campaigns (green dashed = inferred clean event)')
ax.set_ylabel('effectiveness eps')
ax.legend(); plt.tight_layout(); plt.show()
"""))

cells.append(md_cell("## 4. Fouling-rate ranking (slope of eps vs days, median across campaigns)"))
cells.append(code_cell(r"""
rows = []
for hx, camps in all_campaigns.items():
    slopes = []
    for c_start, c_end in camps:
        s = eps.loc[c_start:c_end, hx].dropna()
        if len(s) < 10:
            continue
        x = (s.index - s.index[0]).days.values.astype(float)
        slope, _ = np.polyfit(x, s.values, 1)
        slopes.append(slope)
    if slopes:
        rows.append({'HX': hx, 'n_campaigns': len(slopes),
                     'median_slope_per_day': np.median(slopes),
                     'mean_eps': eps[hx].mean()})

fouling_rank = pd.DataFrame(rows).sort_values('median_slope_per_day').reset_index(drop=True)
print('most negative slope = fouls fastest')
fouling_rank
"""))

cells.append(md_cell(r"""
## 5. Cleaning recommendation (current campaign, project trend forward)

Trigger ตาม CPHT_Cleaning_and_Problem_Control_Plan.docx: clean เมื่อ effectiveness
ลด > 10–15% จาก baseline ของ campaign นั้น ๆ.
"""))
cells.append(code_cell(r"""
TRIGGER_DROP_FRAC = 0.125    # 12.5%, มัธยฐานของช่วง 10–15%

reco_rows = []
last_date = df.index.max()
for hx, camps in all_campaigns.items():
    c_start, c_end = camps[-1]
    s = eps.loc[c_start:c_end, hx].dropna()
    if len(s) < 10:
        continue
    x = (s.index - s.index[0]).days.values.astype(float)
    y = s.values
    slope, intercept = np.polyfit(x, y, 1)
    baseline = np.percentile(y[:max(5, len(y)//10)], 90)
    current  = y[-1]
    drop = (baseline - current) / baseline if baseline else np.nan
    if slope < 0:
        target = baseline * (1 - TRIGGER_DROP_FRAC)
        days = (target - intercept) / slope
        eta = (c_start + pd.Timedelta(days=days)).date()
    else:
        eta = None
    reco_rows.append({
        'HX': hx,
        'campaign_start': c_start.date(),
        'days_in_campaign': (last_date - c_start).days,
        'baseline_eps': round(baseline, 3),
        'current_eps':  round(current, 3),
        'drop_from_baseline_%': round(drop * 100, 1),
        'slope_per_day': round(slope, 5),
        'recommended_clean_by': eta,
        'already_past_trigger': bool(drop >= TRIGGER_DROP_FRAC) if pd.notna(drop) else False,
    })

reco_df = pd.DataFrame(reco_rows).sort_values('drop_from_baseline_%', ascending=False).reset_index(drop=True)
print('as of:', last_date.date())
reco_df
"""))

write_nb(cells, "test_fouling.ipynb")


# ============================================================================
# 3) test_models.ipynb  -- leak-free CIT model baseline (RF / XGB / Ada / Bag / Ridge)
# ============================================================================
cells = []
cells.append(md_cell(r"""
# Scratch 3 — Leak-Free CIT Prediction Baseline

ตรวจสอบว่า:
- ไม่มี target leakage ใน feature matrix (E113A’s cold-side outlet = `1TI116.pv` = CIT,
  เลยต้องตัด `E113A_dT_cold` / `E113A_eps` ออก ใช้แค่ cold-inlet กับ hot-side ของ E113A)
- chronological 80/20 split (ไม่ shuffle เพราะเป็น time-series)
- เปรียบเทียบ baseline 5 ตัว: Ridge / RF / XGBoost / AdaBoost / Bagging
  (LSTM ใช้ใน notebook หลัก `5_HX_fouling_CIT_ranking.ipynb`)
- ดู feature importance ระดับ tag ก่อน aggregate per HX
"""))

cells.append(md_cell("## Setup"))
cells.append(code_cell(SHARED_SETUP))
cells.append(code_cell(LOAD_DATA))
cells.append(code_cell(r"""
CP_CRUDE   = 2.2
RHO_CRUDE  = 850
TARGET_TAG = '1TI116.pv'    # CIT
CHARGE_TAG = '1fi005.pv'
O2_TAG     = '1AI001.pv'
LEAK_TARGET_HX = 'E113A'    # cold_out IS the target -- handle separately
"""))

cells.append(code_cell(PARSE_TAGS))

cells.append(md_cell(r"""
## 1. Build leak-free feature matrix

สำหรับ HX ทุกตัว ยกเว้น E113A: ใช้ `eps`, `dT_cold`, `dT_hot`, `duty_kW` ตามปกติ.
สำหรับ E113A: ใช้แค่ `cold_in` (= `1TI115.pv`, อุณหภูมิก่อนเข้า HX สุดท้าย) และ
`dT_hot` / `duty_kW` ของ residue side — *ไม่* ใส่ `dT_cold` หรือ `eps` เพราะมัน
มี `1TI116.pv` (= CIT) อยู่ในสูตร.
"""))
cells.append(code_cell(r"""
feat = pd.DataFrame(index=df.index)
for hx, s in streams.items():
    leaky = (hx == LEAK_TARGET_HX)
    if not leaky:
        if s['cold_in'] and s['hot_in']:
            denom = (df[s['hot_in']] - df[s['cold_in']]).replace(0, np.nan)
            feat[f'{hx}_eps'] = ((df[s['cold_out']] - df[s['cold_in']]) / denom).clip(-0.5, 1.5)
        if s['cold_in'] and s['cold_out']:
            feat[f'{hx}_dT_cold'] = df[s['cold_out']] - df[s['cold_in']]
        if s['cold_flow'] and s['cold_in'] and s['cold_out']:
            feat[f'{hx}_duty_kW'] = RHO_CRUDE * df[s['cold_flow']] * CP_CRUDE * (df[s['cold_out']] - df[s['cold_in']]) / 3600
        elif s['hot_flow'] and s['hot_in'] and s['hot_out']:
            feat[f'{hx}_duty_kW'] = RHO_CRUDE * df[s['hot_flow']] * CP_CRUDE * (df[s['hot_in']] - df[s['hot_out']]) / 3600
    if s['hot_in'] and s['hot_out']:
        feat[f'{hx}_dT_hot'] = df[s['hot_in']] - df[s['hot_out']]
    if leaky:
        feat[f'{hx}_cold_in'] = df[s['cold_in']]                         # 1TI115.pv -- NOT the target
        if s['hot_flow'] and s['hot_in'] and s['hot_out']:
            feat[f'{hx}_duty_kW'] = RHO_CRUDE * df[s['hot_flow']] * CP_CRUDE * (df[s['hot_in']] - df[s['hot_out']]) / 3600

feat['total_charge'] = df[CHARGE_TAG]
feat['flue_O2']      = df[O2_TAG]

target = df[TARGET_TAG]

assert TARGET_TAG not in feat.columns
assert not [c for c in feat.columns if 'E113A_dT_cold' in c or 'E113A_eps' in c], 'leakage'
print('feature shape:', feat.shape, '-- no leakage cols present')
feat.head(3)
"""))

cells.append(md_cell("## 2. Chronological 80/20 train/test split"))
cells.append(code_cell(r"""
data = feat.copy()
data['CIT'] = target
data = data.dropna()
X = data.drop(columns=['CIT'])
y = data['CIT']

split_idx = int(len(data) * 0.8)
X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
print(f'Train: {X_train.index.min().date()} -> {X_train.index.max().date()}  (n={len(X_train)})')
print(f'Test:  {X_test.index.min().date()} -> {X_test.index.max().date()}  (n={len(X_test)})')

fig, ax = plt.subplots(figsize=(14, 3.5))
ax.plot(y_train.index, y_train, lw=1, color='tab:blue', label='train')
ax.plot(y_test.index,  y_test,  lw=1, color='tab:orange', label='test')
ax.axvline(X_test.index[0], color='black', ls='--', lw=1)
ax.set_ylabel('CIT (C)'); ax.set_title('CIT — train/test split')
ax.legend(); plt.tight_layout(); plt.show()
"""))

cells.append(md_cell("## 3. Train 5 baseline models"))
cells.append(code_cell(r"""
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, AdaBoostRegressor, BaggingRegressor
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
import xgboost as xgb

models = {
    'Ridge':        Ridge(alpha=1.0),
    'RandomForest': RandomForestRegressor(n_estimators=300, random_state=42),
    'XGBoost':      xgb.XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05, random_state=42),
    'AdaBoost':     AdaBoostRegressor(n_estimators=100, random_state=42),
    'Bagging':      BaggingRegressor(n_estimators=100, random_state=42),
}

results = []
fitted = {}
for name, m in models.items():
    m.fit(X_train, y_train)
    pred = m.predict(X_test)
    results.append({
        'model': name,
        'R2':   r2_score(y_test, pred),
        'MAE':  mean_absolute_error(y_test, pred),
        'RMSE': np.sqrt(mean_squared_error(y_test, pred)),
        'within_5C_%':  (np.abs(pred - y_test) <= 5).mean()  * 100,
        'within_10C_%': (np.abs(pred - y_test) <= 10).mean() * 100,
    })
    fitted[name] = m

pd.DataFrame(results).sort_values('within_10C_%', ascending=False).reset_index(drop=True)
"""))

cells.append(md_cell(r"""
**หมายเหตุเรื่อง R²:** test window (~20% สุดท้าย) เป็นช่วงเดินเครื่องนิ่งกว่าช่วง train
มาก (CIT std ~2.6°C vs ~7.6°C ใน train) — R² ที่เป็นลบจึงเป็นผลของ variance ที่ test
ต่ำ ไม่ใช่โมเดลพยากรณ์ไม่ได้ ดู `within_10C_%` ตามที่ดีไซน์เดิม
(`CIT_Model_Dashboard_Solution_Design.docx`) ระบุไว้ว่าเกณฑ์รับคือ > 90% within ±5–10°C.
"""))

cells.append(md_cell("## 4. Random Forest feature importance — top 15 individual features"))
cells.append(code_cell(r"""
rf_imp = pd.Series(fitted['RandomForest'].feature_importances_, index=X.columns)\
            .sort_values(ascending=False)
rf_imp.head(15)
"""))

cells.append(md_cell("## 5. Aggregate per HX → HX-level importance to CIT"))
cells.append(code_cell(r"""
hx_imp = {}
for hx in HX_CONFIG.keys():
    cols = [c for c in X.columns if c.startswith(hx + '_')]
    if cols:
        hx_imp[hx] = rf_imp[cols].sum()
hx_imp_s = pd.Series(hx_imp).sort_values(ascending=False)

fig, ax = plt.subplots(figsize=(9, 5))
ax.barh(hx_imp_s.index, hx_imp_s.values, color='tab:purple')
ax.set_xlabel('RF feature importance (aggregated per HX)')
ax.invert_yaxis(); ax.set_title('HX importance to CIT')
plt.tight_layout(); plt.show()
hx_imp_s
"""))

write_nb(cells, "test_models.ipynb")
