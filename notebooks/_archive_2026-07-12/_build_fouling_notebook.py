"""
Helper script: builds 5_HX_fouling_CIT_ranking.ipynb from cell definitions.
Run once: python _build_fouling_notebook.py
"""
import json
from pathlib import Path

def code_cell(source):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.strip("\n").splitlines(keepends=True)
    }

def md_cell(source):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.strip("\n").splitlines(keepends=True)
    }

cells = []

# ── TITLE ────────────────────────────────────────────────────────────────────
cells.append(md_cell(r"""
# Heat Exchanger Fouling & CIT Importance Ranking
**Bangchak Plant 3 TPU | Crude Preheat Train (CPHT) | CIT Optimization Project**

**Goal:** for each of the 16 preheat-train heat exchangers (E101AB ... E113A),
learn how fast it fouls, rank how much it matters to CIT (Coil Inlet
Temperature, `1TI116.pv`, the furnace feed temperature), and recommend when
each one should next be cleaned. Multiple ML models are then compared for
predicting CIT from the engineered HX-health features.

**Data:** `Process_information_cleaned.csv` (output of `1_cleaning_data_process.ipynb`)
— 96 tags, daily, with turnaround/shutdown (TAM) periods already removed.

**Physics reference:** `Equations_Reference_Fouling_Combustion_NOx.docx` and
`CPHT_Cleaning_and_Problem_Control_Plan.docx`
(`Optimization Crude Preheat Train Bangchak/` folder). Key equations used here:
- Thermal effectiveness `eps = (T_cold,out - T_cold,in) / (T_hot,in - T_cold,in)` (Eq. 9 cold-side form)
  — falls as a HX fouls; used as the primary fouling indicator because true
  fouling resistance `Rf = 1/U_fouling - 1/U_clean` (Eq. 13) needs exchanger
  area `A` and clean-`U`, which are only on hand for one of the sixteen HX.
- Duty `Q = rho * V * cp * dT / 3600` kW (Eq. 1-2), with `cp = 2.2 kJ/kg.K`,
  `rho = 850 kg/m3` (assumed crude properties, per the reference doc — replace
  with real assay values when available).
- Cleaning trigger: thermal effectiveness drop **> 10-15%** vs campaign-start
  baseline (Section 2 of the Cleaning & Problem Control Plan).

**Sections:**
1. Load cleaned data
2. HX configuration & per-HX feature engineering (dT, effectiveness, duty)
3. Shutdown (TAM) segment detection + per-HX local clean-event inference
4. Fouling-rate ranking (how fast does each HX foul)
5. Cleaning recommendation (current campaign, projected trigger date)
6. Leak-free feature matrix for CIT prediction
7. Model comparison: Ridge, Random Forest, XGBoost, AdaBoost, Bagging, LSTM
8. HX importance ranking (feature importance vs CIT)
9. Combined HX cleaning-priority table (fouling rate x CIT importance)
10. Summary & limitations
"""))

# ── CELL: IMPORTS / CONFIG ──────────────────────────────────────────────────
cells.append(md_cell("## 0. Imports & Configuration"))
cells.append(code_cell(r"""
import warnings, os
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

plt.rcParams.update({'figure.dpi': 110, 'font.size': 10,
                     'axes.grid': True, 'grid.alpha': 0.3})

DATA_FILE = Path(r'C:\Desktop\Bangchak Internship 2026\Data\Process_information_cleaned.csv')
FIG_DIR = Path(r'C:\Desktop\Bangchak Internship 2026\furnace-optimization\figures\fouling_analysis')
OUT_DIR = Path(r'C:\Desktop\Bangchak Internship 2026\furnace-optimization\outputs')
FIG_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_TAG = '1TI116.pv'   # CIT - Coil Inlet Temperature to furnace F101
CHARGE_TAG = '1fi005.pv'   # total crude charge
O2_TAG = '1AI001.pv'       # flue gas O2 %

CP_CRUDE = 2.2   # kJ/kg-K, assumed (Equations_Reference doc + Data Parameter sheet)
RHO_CRUDE = 850  # kg/m3, assumed

TRIGGER_DROP_FRAC = 0.125   # cleaning trigger: 10-15% effectiveness drop (Cleaning & Problem Control Plan)
MIN_CAMPAIGN_DAYS = 20      # minimum days for a campaign to be used in slope fitting

print('Data file exists:', DATA_FILE.exists())
"""))

# ── CELL: LOAD DATA ─────────────────────────────────────────────────────────
cells.append(md_cell("## 1. Load Cleaned Data"))
cells.append(code_cell(r"""
df = pd.read_csv(DATA_FILE, index_col='Timestamp', parse_dates=True)
print('Shape:', df.shape)
print('Date range:', df.index.min().date(), '->', df.index.max().date())
df[[TARGET_TAG, CHARGE_TAG, O2_TAG]].describe().T
"""))

# ── CELL: HX_CONFIG ─────────────────────────────────────────────────────────
cells.append(md_cell(r"""
## 2. HX Configuration & Feature Engineering

`HX_CONFIG` lists, for each of the 16 heat exchangers, the cold-side (crude)
and hot-side (utility stream) tags, ported from the authoritative mapping
already defined in `1_cleaning_data_process.ipynb` (cell 39) and cross-checked
against the `HX Breakdown` sheet of `Data Parameter For Project bangchak.xlsx`.
"""))
cells.append(code_cell(r"""
HX_CONFIG = {
    'E101AB': {'title': 'E101AB - Crude vs 1st Side Run',
        'cold': [('1FI007.pv','Crude Inlet Flow','M3/HR'), ('1TI102.pv','Crude Inlet Temp','DEGC'), ('1TI101.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FI010.pv','1SR Inlet Flow','M3/HR'), ('1TI194.pv','1SR Inlet Temp','DEGC'), ('1TI103.pv','1SR Outlet Temp','DEGC')]},
    'E101CD': {'title': 'E101CD - Crude vs 1st Side Run',
        'cold': [('1FI008.pv','Crude Inlet Flow','M3/HR'), ('1TI102.pv','Crude Inlet Temp','DEGC'), ('1TI104.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FI011.pv','1SR Inlet Flow','M3/HR'), ('1TI194.pv','1SR Inlet Temp','DEGC'), ('1TI105.pv','1SR Outlet Temp','DEGC')]},
    'E101EF': {'title': 'E101EF - Crude vs 1st Side Run',
        'cold': [('1FI009.pv','Crude Inlet Flow','M3/HR'), ('1TI102.pv','Crude Inlet Temp','DEGC'), ('1TI109.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FI012.pv','1SR Inlet Flow','M3/HR'), ('1TI194.pv','1SR Inlet Temp','DEGC'), ('1TI110.pv','1SR Outlet Temp','DEGC')]},
    'E102': {'title': 'E102 - Crude vs Kerosene',
        'cold': [('1TI107.pv','Crude Inlet Temp','DEGC'), ('1TI106.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1TI165.pv','Kero Inlet Temp','DEGC'), ('1TI108.pv','Kero Outlet Temp','DEGC'), ('1FC055.pv','Kero Outlet Flow','M3/HR')]},
    'E103AB': {'title': 'E103AB - Crude vs 2nd Side Run (2RS-1)',
        'cold': [('1FI015.pv','Crude Inlet Flow','M3/HR'), ('1TI225.pv','Crude Inlet Temp','DEGC'), ('1TI136.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FI018.pv','2RS-1 Inlet Flow','M3/HR'), ('4TI107.pv','2RS Inlet Temp','DEGC'), ('1TI137.pv','2RS-1 Outlet Temp','DEGC')]},
    'E104': {'title': 'E104 - Crude vs 2nd Side Run',
        'cold': [('1FI015.pv','Crude Inlet Flow','M3/HR'), ('1TI136.pv','Crude Inlet Temp (from E103)','DEGC'), ('1TI112.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1TI195.pv','2RS Inlet Temp','DEGC'), ('4TI115.pv','2RS Outlet Temp','DEGC')]},
    'E105AB': {'title': 'E105AB - Crude vs 3rd Side Run',
        'cold': [('1FI015.pv','Crude Inlet Flow','M3/HR'), ('1TI112.pv','Crude Inlet Temp (from E104)','DEGC'), ('1TI114.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FC035.pv','3RS Flow','M3/HR'), ('1TI195.pv','3RS Inlet Temp','DEGC'), ('1TI113.pv','3RS Outlet Temp','DEGC')]},
    'E106AB': {'title': 'E106AB - Crude vs 2nd Side Run (2RS-2)',
        'cold': [('1FI016.pv','Crude Inlet Flow','M3/HR'), ('1TI225.pv','Crude Inlet Temp','DEGC'), ('1TI128.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FI019.pv','2RS-2 Inlet Flow','M3/HR'), ('4TI107.pv','2RS Inlet Temp','DEGC'), ('1TI129.pv','2RS-2 Outlet Temp','DEGC')]},
    'E107AB': {'title': 'E107AB - Crude vs Gas Oil',
        'cold': [('1FI016.pv','Crude Inlet Flow','M3/HR'), ('1TI128.pv','Crude Inlet Temp (from E106)','DEGC'), ('1TI130.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1TI135.pv','GO Inlet Temp (from E109)','DEGC'), ('1TI131.pv','GO Outlet Temp','DEGC')]},
    'E108AB': {'title': 'E108AB - Crude vs Residue',
        'cold': [('1FI016.pv','Crude Inlet Flow','M3/HR'), ('1TI130.pv','Crude Inlet Temp (from E107)','DEGC'), ('1TI132.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('439FI003.pv','Residue Flow','M3/HR'), ('1TI127.pv','Residue Inlet Temp','DEGC'), ('1TI133.pv','Residue Outlet Temp','DEGC')]},
    'E109AB': {'title': 'E109AB - Crude vs Gas Oil',
        'cold': [('1FI016.pv','Crude Inlet Flow','M3/HR'), ('1TI132.pv','Crude Inlet Temp (from E108)','DEGC'), ('1TI134.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1TI163.pv','GO Inlet Temp','DEGC'), ('1TI135.pv','GO Outlet Temp','DEGC')]},
    'E110ABC': {'title': 'E110ABC - Crude vs Residue',
        'cold': [('1FI017.pv','Crude Inlet Flow','M3/HR'), ('1TI225.pv','Crude Inlet Temp','DEGC'), ('1TI124.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('439FI003.pv','Residue Flow','M3/HR'), ('1TI133.pv','Residue Inlet Temp','DEGC'), ('1TI122.pv','Residue Outlet Temp','DEGC')]},
    'E111': {'title': 'E111 - Crude vs 3rd Side Run',
        'cold': [('1FI017.pv','Crude Inlet Flow','M3/HR'), ('1TI124.pv','Crude Inlet Temp (from E110)','DEGC'), ('1TI123.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FC035.pv','3RS Flow','M3/HR'), ('1TI113.pv','3RS Inlet Temp (from E105)','DEGC'), ('1TI125.pv','3RS Outlet Temp','DEGC')]},
    'E112AB': {'title': 'E112AB - Crude vs Residue',
        'cold': [('1FI017.pv','Crude Inlet Flow','M3/HR'), ('1TI123.pv','Crude Inlet Temp (from E111)','DEGC'), ('1TI126.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('439FI003.pv','Residue Flow','M3/HR'), ('1TI117.pv','Residue Inlet Temp','DEGC'), ('1TI127.pv','Residue Outlet Temp','DEGC')]},
    'E112C': {'title': 'E112C - Crude vs Residue',
        'cold': [('1FI017.pv','Crude Inlet Flow','M3/HR'), ('1TI123.pv','Crude Inlet Temp (from E111)','DEGC'), ('1TI114.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('439FI003.pv','Residue Flow','M3/HR'), ('1TI117.pv','Residue Inlet Temp','DEGC'), ('1TI117B.pv','Residue Outlet Temp','DEGC')]},
    'E113A': {'title': 'E113A - Crude vs Residue (last HX before Furnace)',
        'cold': [('1TI115.pv','Crude Inlet Temp','DEGC'), ('1TI116.pv','Crude Outlet Temp (CIT)','DEGC'), ('1PI003.pv','Pressure Inlet Furnace','BARG')],
        'hot':  [('439FI003.pv','Residue Flow','M3/HR'), ('1TI161.pv','Residue from Distillation','DEGC'), ('1TI117.pv','Residue Outlet Temp','DEGC'), ('1PI055.pv','Residue Inlet Pressure','BARG'), ('1PI056.pv','Residue Outlet Pressure','BARG')]},
}

LEAK_TARGET_HX = 'E113A'  # cold-side outlet of E113A IS the target (CIT) -- handled separately, see section 6

print(f'Defined {len(HX_CONFIG)} heat exchangers')
"""))

cells.append(code_cell(r"""
def classify_side(items):
    # Pulls (flow_tag, inlet_temp_tag, outlet_temp_tag) out of a cold/hot tag list.
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
    # E113A hot side has 'Residue from Distillation' with no inlet/outlet wording
    if t_in is None and unclassified:
        t_in = unclassified[0]
    return flow, t_in, t_out

def parse_hx(cfg):
    cold_flow, cold_in, cold_out = classify_side(cfg['cold'])
    hot_flow, hot_in, hot_out = classify_side(cfg['hot'])
    return dict(cold_flow=cold_flow, cold_in=cold_in, cold_out=cold_out,
                hot_flow=hot_flow, hot_in=hot_in, hot_out=hot_out)

streams = {hx: parse_hx(cfg) for hx, cfg in HX_CONFIG.items()}
pd.DataFrame(streams).T
"""))

cells.append(md_cell(r"""
### Per-HX features

- `dT_cold` = crude outlet - crude inlet (degC gained by the crude)
- `dT_hot` = utility inlet - utility outlet (degC given up by the hot stream)
- `eps` = thermal effectiveness, Eq. 9 cold-side form: `(T_cold,out - T_cold,in) / (T_hot,in - T_cold,in)`
  — dimensionless, robust to changing inlet conditions; **falls as the HX fouls**
- `duty_kW` = `rho * V * cp * dT / 3600`, using cold-side flow when available,
  otherwise falling back to the hot-side flow (`Q_hot ~= Q_cold` at steady state, Eq. 1-2)
"""))
cells.append(code_cell(r"""
eps_df = pd.DataFrame(index=df.index)
dT_cold_df = pd.DataFrame(index=df.index)
duty_df = pd.DataFrame(index=df.index)

for hx, s in streams.items():
    if s['cold_in'] and s['cold_out']:
        dT_cold_df[hx] = df[s['cold_out']] - df[s['cold_in']]
    if s['cold_in'] and s['cold_out'] and s['hot_in']:
        denom = (df[s['hot_in']] - df[s['cold_in']]).replace(0, np.nan)
        eps_df[hx] = ((df[s['cold_out']] - df[s['cold_in']]) / denom).clip(-0.5, 1.5)
    if s['cold_flow'] and s['cold_in'] and s['cold_out']:
        duty_df[hx] = RHO_CRUDE * df[s['cold_flow']] * CP_CRUDE * (df[s['cold_out']] - df[s['cold_in']]) / 3600
    elif s['hot_flow'] and s['hot_in'] and s['hot_out']:
        duty_df[hx] = RHO_CRUDE * df[s['hot_flow']] * CP_CRUDE * (df[s['hot_in']] - df[s['hot_out']]) / 3600

print('Effectiveness (eps) summary:')
eps_df.describe().T[['mean','std','min','max']].round(3)
"""))

cells.append(code_cell(r"""
fig, axes = plt.subplots(4, 4, figsize=(18, 12), sharex=True)
axes = axes.flatten()
for i, hx in enumerate(HX_CONFIG.keys()):
    ax = axes[i]
    if hx in eps_df.columns:
        ax.plot(eps_df.index, eps_df[hx], lw=0.6, color='tab:blue', alpha=0.8)
        ax.plot(eps_df.index, eps_df[hx].rolling(14, min_periods=5).mean(), lw=1.5, color='tab:red')
    ax.set_title(hx, fontsize=10)
    ax.tick_params(axis='x', labelrotation=45, labelsize=7)
for j in range(len(HX_CONFIG), len(axes)):
    axes[j].set_visible(False)
fig.suptitle('Thermal effectiveness (eps) per HX -- blue=daily, red=14-day rolling mean', y=1.01)
plt.tight_layout()
plt.savefig(FIG_DIR / 'eps_all_hx.png', dpi=110, bbox_inches='tight')
plt.show()
"""))

# ── CELL: SEGMENTS ───────────────────────────────────────────────────────────
cells.append(md_cell(r"""
## 3. Shutdown (TAM) Segments + Per-HX Local Clean-Event Inference

There are no recorded per-HX maintenance dates, so cleaning events are
**inferred** from the data itself, in two layers:

1. **Global TAM segments** — re-detected here from date gaps in the already-
   shutdown-removed CSV (`1_cleaning_data_process.ipynb` strips TAM windows,
   leaving a gap in the daily index). These are hard plant-wide boundaries.
2. **Local per-HX clean events** — within each global segment, a sudden upward
   jump in a HX's smoothed effectiveness (more than 2.5 std of its daily
   effectiveness change) is treated as an online/local clean of that exchanger.
   This lets HX that get cleaned independently of a full TAM show up as
   separate fouling "campaigns".
"""))
cells.append(code_cell(r"""
day_gap = df.index.to_series().diff().dt.days
seg_id = (day_gap > 1).cumsum()
segments = [(idx.min(), idx.max()) for _, idx in df.groupby(seg_id).groups.items()]

print(f'{len(segments)} global TAM segment(s):')
for s in segments:
    print(' ', s[0].date(), '->', s[1].date(), f'({(s[1]-s[0]).days} days)')
"""))

cells.append(code_cell(r"""
def detect_campaigns(series, seg_start, seg_end):
    s = series.loc[seg_start:seg_end].dropna()
    if len(s) < MIN_CAMPAIGN_DAYS:
        return [(seg_start, seg_end)]
    smooth = s.rolling(7, min_periods=3).mean()
    delta = smooth.diff()
    thresh = delta.std(skipna=True) * 2.5
    if not np.isfinite(thresh) or thresh <= 0:
        return [(seg_start, seg_end)]
    jump_days = sorted(delta.index[delta > thresh])
    boundaries, last = [seg_start], None
    for d in jump_days:
        if last is None or (d - last).days > 5:
            boundaries.append(d)
        last = d
    boundaries.append(seg_end + pd.Timedelta(days=1))
    boundaries = sorted(set(boundaries))
    campaigns = []
    for i in range(len(boundaries) - 1):
        c_start, c_end = boundaries[i], boundaries[i + 1] - pd.Timedelta(days=1)
        if c_end >= c_start and (c_end - c_start).days + 1 >= MIN_CAMPAIGN_DAYS:
            campaigns.append((c_start, c_end))
    return campaigns if campaigns else [(seg_start, seg_end)]

all_campaigns = {}
for hx in eps_df.columns:
    camps = []
    for seg_start, seg_end in segments:
        camps.extend(detect_campaigns(eps_df[hx], seg_start, seg_end))
    all_campaigns[hx] = camps

n_camp = {hx: len(c) for hx, c in all_campaigns.items()}
print('Campaigns detected per HX:')
print(pd.Series(n_camp).sort_values(ascending=False))
"""))

cells.append(code_cell(r"""
# visualize campaign boundaries for the fastest-fouling-looking HX (most campaigns)
example_hx = pd.Series(n_camp).idxmax()
fig, ax = plt.subplots(figsize=(14, 4))
ax.plot(eps_df.index, eps_df[example_hx], lw=0.6, color='gray', alpha=0.6, label='daily eps')
ax.plot(eps_df.index, eps_df[example_hx].rolling(7, min_periods=3).mean(), lw=1.5, color='tab:blue', label='7-day rolling mean')
for c_start, c_end in all_campaigns[example_hx]:
    ax.axvline(c_start, color='tab:green', ls='--', lw=1, alpha=0.7)
ax.set_title(f'{example_hx}: detected cleaning campaigns (green dashed = inferred clean event)')
ax.set_ylabel('Effectiveness (eps)')
ax.legend()
plt.tight_layout()
plt.savefig(FIG_DIR / f'campaigns_{example_hx}.png', dpi=110, bbox_inches='tight')
plt.show()
"""))

# ── CELL: FOULING RATE RANKING ──────────────────────────────────────────────
cells.append(md_cell(r"""
## 4. Fouling-Rate Ranking

For each campaign, fit a linear trend of effectiveness vs. days-since-clean.
The slope is the fouling rate for that campaign (negative = effectiveness
declining = fouling). The **median slope across campaigns** ranks each HX by
how fast it typically fouls.
"""))
cells.append(code_cell(r"""
rows = []
for hx, camps in all_campaigns.items():
    slopes = []
    for c_start, c_end in camps:
        s = eps_df.loc[c_start:c_end, hx].dropna()
        if len(s) < 10:
            continue
        x = (s.index - s.index[0]).days.values.astype(float)
        slope, _ = np.polyfit(x, s.values, 1)
        slopes.append(slope)
    if slopes:
        rows.append({'HX': hx, 'n_campaigns': len(slopes),
                      'median_fouling_rate_eps_per_day': np.median(slopes),
                      'mean_eps': eps_df[hx].mean()})

fouling_rank = pd.DataFrame(rows).sort_values('median_fouling_rate_eps_per_day').reset_index(drop=True)
print('Fouling rate ranking (most negative slope = fouls fastest):')
fouling_rank
"""))

cells.append(code_cell(r"""
fig, ax = plt.subplots(figsize=(9, 6))
colors = ['tab:red' if v < 0 else 'tab:green' for v in fouling_rank['median_fouling_rate_eps_per_day']]
ax.barh(fouling_rank['HX'], fouling_rank['median_fouling_rate_eps_per_day'], color=colors)
ax.axvline(0, color='black', lw=0.8)
ax.set_xlabel('Median fouling rate (eps change per day)')
ax.set_title('HX Fouling Rate Ranking (more negative = fouls faster)')
ax.invert_yaxis()
plt.tight_layout()
plt.savefig(FIG_DIR / 'fouling_rate_ranking.png', dpi=110, bbox_inches='tight')
plt.show()
"""))

# ── CELL: CLEANING RECOMMENDATION ───────────────────────────────────────────
cells.append(md_cell(r"""
## 5. Cleaning Recommendation (Current Campaign)

For each HX's **current (most recent) campaign**, project the fitted trend
forward and flag when effectiveness is expected to cross the
**10-15% drop-from-baseline trigger** (Cleaning & Problem Control Plan,
Section 2). If the trigger has already been crossed, the HX is flagged for
cleaning now rather than at a stale past date.
"""))
cells.append(code_cell(r"""
last_date = df.index.max()
reco_rows = []
for hx, camps in all_campaigns.items():
    c_start, c_end = camps[-1]
    s = eps_df.loc[c_start:c_end, hx].dropna()
    if len(s) < 10:
        continue
    x = (s.index - s.index[0]).days.values.astype(float)
    y = s.values
    slope, intercept = np.polyfit(x, y, 1)
    baseline = np.percentile(y[:max(5, len(y) // 10)], 90)
    current = y[-1]
    drop_frac = (baseline - current) / baseline if baseline else np.nan
    past_trigger = bool(pd.notna(drop_frac) and drop_frac >= TRIGGER_DROP_FRAC)

    if past_trigger:
        action = 'Clean now (past trigger)'
    elif slope >= -1e-5:
        action = 'Stable / monitor'
    else:
        target_eps = baseline * (1 - TRIGGER_DROP_FRAC)
        days_from_start = (target_eps - intercept) / slope
        eta = c_start + pd.Timedelta(days=days_from_start)
        horizon_days = (eta - last_date).days
        action = eta.date().isoformat() if 0 <= horizon_days <= 1095 else 'Stable / long horizon (>3y)'

    reco_rows.append({
        'HX': hx, 'campaign_start': c_start.date(), 'days_in_campaign': (last_date - c_start).days,
        'baseline_eps': round(baseline, 3), 'current_eps': round(current, 3),
        'drop_from_baseline_%': round(drop_frac * 100, 1) if pd.notna(drop_frac) else np.nan,
        'past_trigger': past_trigger, 'recommended_action': action,
    })

cleaning_reco = pd.DataFrame(reco_rows).sort_values('drop_from_baseline_%', ascending=False).reset_index(drop=True)
cleaning_reco
"""))

# ── CELL: LEAK-FREE FEATURE MATRIX ──────────────────────────────────────────
cells.append(md_cell(r"""
## 6. Leak-Free Feature Matrix for CIT Prediction

**Important:** E113A is the last exchanger before the furnace -- its
cold-side *outlet* tag, `1TI116.pv`, **is** CIT, the prediction target. Any
feature built from E113A's `dT_cold` or `eps` (both use `1TI116.pv` directly
in their formula) would leak the answer into the model. For CIT prediction we
therefore use, from E113A, only its **non-leaky** inputs: cold inlet temp
(`1TI115.pv`, i.e. the train's state just before the final HX), hot-side
duty/dT (residue stream, unrelated to CIT), excluding `dT_cold`/`eps`.
E113A's own `eps`/`dT_cold` are still valid for the fouling-rate ranking
above (sections 3-5) since those are diagnostic, not predictive, uses.

Process-level features added: total crude charge rate and flue-gas O2 (both
contemporaneous plant-state signals, not furnace-response variables like fuel
flow or COT, which would be reacting *to* CIT rather than driving it).
"""))
cells.append(code_cell(r"""
feat = pd.DataFrame(index=df.index)

for hx, s in streams.items():
    leaky = (hx == LEAK_TARGET_HX)
    if not leaky:
        if hx in eps_df.columns:
            feat[f'{hx}_eps'] = eps_df[hx]
        if hx in dT_cold_df.columns:
            feat[f'{hx}_dT_cold'] = dT_cold_df[hx]
        if hx in duty_df.columns:
            feat[f'{hx}_duty_kW'] = duty_df[hx]
    if s['hot_in'] and s['hot_out']:
        feat[f'{hx}_dT_hot'] = df[s['hot_in']] - df[s['hot_out']]
    if leaky:
        feat[f'{hx}_cold_in'] = df[s['cold_in']]  # 1TI115.pv -- pre-final-HX temp, not CIT itself

feat['total_charge'] = df[CHARGE_TAG]
feat['flue_O2'] = df[O2_TAG]

target = df[TARGET_TAG]

leak_check = [c for c in feat.columns if f'{LEAK_TARGET_HX}_dT_cold' in c or f'{LEAK_TARGET_HX}_eps' in c]
assert TARGET_TAG not in feat.columns and not leak_check, 'Target leakage detected!'

data = feat.copy()
data['CIT'] = target
data = data.dropna()
print('Feature matrix shape (after dropna):', data.shape)
print('No target-leakage columns present.')

X = data.drop(columns=['CIT'])
y = data['CIT']
"""))

# ── CELL: TRAIN/TEST SPLIT ──────────────────────────────────────────────────
cells.append(md_cell("### Chronological Train/Test Split\n\nNon-overlapping, time-ordered 80/20 split (no shuffling -- this is daily process data with autocorrelation)."))
cells.append(code_cell(r"""
split_idx = int(len(data) * 0.8)
X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

print(f'Train: {X_train.index.min().date()} -> {X_train.index.max().date()}  (n={len(X_train)})')
print(f'Test:  {X_test.index.min().date()} -> {X_test.index.max().date()}  (n={len(X_test)})')

fig, ax = plt.subplots(figsize=(14, 4))
ax.plot(y_train.index, y_train, lw=1, color='tab:blue', label='Train')
ax.plot(y_test.index, y_test, lw=1, color='tab:orange', label='Test')
ax.axvline(X_test.index[0], color='black', ls='--', lw=1)
ax.set_ylabel('CIT (C)')
ax.set_title('CIT - Train/Test Split')
ax.legend()
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
plt.tight_layout()
plt.show()
"""))

# ── CELL: MODELS ─────────────────────────────────────────────────────────────
cells.append(md_cell(r"""
## 7. Model Comparison

Ridge (regularized linear baseline), Random Forest, XGBoost, AdaBoost,
Bagging, and an LSTM (7-day lookback window) are trained on the same
leak-free feature matrix and compared on the held-out chronological test set.
"""))
cells.append(code_cell(r"""
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, AdaBoostRegressor, BaggingRegressor
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
import xgboost as xgb

sk_models = {
    'Ridge': Ridge(alpha=1.0),
    'RandomForest': RandomForestRegressor(n_estimators=300, random_state=42),
    'XGBoost': xgb.XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05, random_state=42),
    'AdaBoost': AdaBoostRegressor(n_estimators=100, random_state=42),
    'Bagging': BaggingRegressor(n_estimators=100, random_state=42),
}

def eval_predictions(name, y_true, pred):
    return {
        'model': name,
        'R2': r2_score(y_true, pred),
        'MAE': mean_absolute_error(y_true, pred),
        'RMSE': np.sqrt(mean_squared_error(y_true, pred)),
        'within_5C_%': (np.abs(pred - y_true) <= 5).mean() * 100,
        'within_10C_%': (np.abs(pred - y_true) <= 10).mean() * 100,
    }

results = []
fitted = {}
predictions = {}
for name, m in sk_models.items():
    m.fit(X_train, y_train)
    pred = m.predict(X_test)
    results.append(eval_predictions(name, y_test.values, pred))
    fitted[name] = m
    predictions[name] = pred

print('Trained:', list(sk_models.keys()))
"""))

cells.append(code_cell(r"""
from sklearn.preprocessing import StandardScaler
from tensorflow import keras
from tensorflow.keras import layers

ENROL = 7
sx = StandardScaler().fit(X_train)
sy = StandardScaler().fit(y_train.values.reshape(-1, 1))
Xtr_s, Xte_s = sx.transform(X_train), sx.transform(X_test)
ytr_s = sy.transform(y_train.values.reshape(-1, 1)).flatten()
yte_s = sy.transform(y_test.values.reshape(-1, 1)).flatten()

def make_windows(arr, tgt, window):
    Xw, yw = [], []
    for i in range(window, len(arr)):
        Xw.append(arr[i - window:i]); yw.append(tgt[i])
    return np.array(Xw), np.array(yw)

Xtr_w, ytr_w = make_windows(Xtr_s, ytr_s, ENROL)
Xte_w, yte_w = make_windows(Xte_s, yte_s, ENROL)

lstm = keras.Sequential([
    layers.Input(shape=(ENROL, Xtr_w.shape[2])),
    layers.LSTM(32),
    layers.Dense(16, activation='relu'),
    layers.Dense(1),
])
lstm.compile(optimizer=keras.optimizers.Adam(learning_rate=0.005), loss='mse')
es = keras.callbacks.EarlyStopping(monitor='loss', patience=20, restore_best_weights=True)
lstm.fit(Xtr_w, ytr_w, epochs=200, batch_size=32, callbacks=[es], verbose=0)

pred_lstm_s = lstm.predict(Xte_w, verbose=0).flatten()
pred_lstm = sy.inverse_transform(pred_lstm_s.reshape(-1, 1)).flatten()
y_test_lstm = sy.inverse_transform(yte_w.reshape(-1, 1)).flatten()

results.append(eval_predictions('LSTM', y_test_lstm, pred_lstm))
print('LSTM trained (window =', ENROL, 'days)')
"""))

cells.append(code_cell(r"""
results_df = pd.DataFrame(results).sort_values('within_10C_%', ascending=False).reset_index(drop=True)
results_df
"""))

cells.append(md_cell(r"""
**Reading R2 here:** the chronological test window (most recent ~20% of days)
happens to be an unusually stable operating period (CIT std ~2.6C vs ~7.6C in
the training window), so R2 can look poor or negative even when absolute
errors are small -- R2 is normalized by test-set variance, and that variance
collapses in this window. This exact pattern was also seen in the prior
synthetic-data pipeline (`CPHT_CIT_Pipeline_v1.ipynb`: R2 = -1.46 but 90.4%
within +/-10C). The project's own acceptance criterion
(`CIT_Model_Dashboard_Solution_Design.docx`) is **>90% of predictions within
+/-5 to 10C**, not R2 -- use the `within_10C_%` column as the primary score.
"""))

cells.append(code_cell(r"""
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
axes[0].barh(results_df['model'], results_df['within_10C_%'], color='tab:blue')
axes[0].set_xlabel('% predictions within +/-10C')
axes[0].set_title('Model Comparison - Tolerance Hit Rate')
axes[0].axvline(90, color='red', ls='--', lw=1, label='90% target')
axes[0].legend()

axes[1].barh(results_df['model'], results_df['MAE'], color='tab:orange')
axes[1].set_xlabel('MAE (C)')
axes[1].set_title('Model Comparison - Mean Absolute Error')

plt.tight_layout()
plt.savefig(FIG_DIR / 'model_comparison.png', dpi=110, bbox_inches='tight')
plt.show()
"""))

cells.append(code_cell(r"""
best_name = results_df.iloc[0]['model']
best_pred = pred_lstm if best_name == 'LSTM' else predictions[best_name]
best_idx = y_test_lstm if best_name == 'LSTM' else y_test.values
best_dates = X_test.index[ENROL:] if best_name == 'LSTM' else X_test.index

fig, ax = plt.subplots(figsize=(14, 4.5))
ax.plot(best_dates, best_idx, lw=1.3, color='tab:blue', label='Actual CIT')
ax.plot(best_dates, best_pred, lw=1.3, color='tab:red', alpha=0.8, label=f'Predicted ({best_name})')
ax.fill_between(best_dates, best_idx - 10, best_idx + 10, color='gray', alpha=0.15, label='+/-10C band')
ax.set_ylabel('CIT (C)')
ax.set_title(f'Best model ({best_name}) - Actual vs Predicted CIT (test period)')
ax.legend()
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
plt.tight_layout()
plt.savefig(FIG_DIR / 'best_model_actual_vs_predicted.png', dpi=110, bbox_inches='tight')
plt.show()
print('Best model by within_10C_%:', best_name)
"""))

# ── CELL: TIMESERIES CV ─────────────────────────────────────────────────────
cells.append(md_cell("### Sanity Check: Blocked Time-Series Cross-Validation\n\nA single train/test split can be misleading on a short, regime-shifting series. `TimeSeriesSplit` re-fits Random Forest across five expanding windows for a fuller picture."))
cells.append(code_cell(r"""
from sklearn.model_selection import TimeSeriesSplit

tscv = TimeSeriesSplit(n_splits=5)
cv_rows = []
for fold, (tr_idx, te_idx) in enumerate(tscv.split(X), start=1):
    m = RandomForestRegressor(n_estimators=300, random_state=42)
    m.fit(X.iloc[tr_idx], y.iloc[tr_idx])
    pred = m.predict(X.iloc[te_idx])
    cv_rows.append({'fold': fold, 'test_start': X.index[te_idx[0]].date(), 'test_end': X.index[te_idx[-1]].date(),
                     'R2': r2_score(y.iloc[te_idx], pred),
                     'within_10C_%': (np.abs(pred - y.iloc[te_idx].values) <= 10).mean() * 100})
pd.DataFrame(cv_rows)
"""))

# ── CELL: HX IMPORTANCE ─────────────────────────────────────────────────────
cells.append(md_cell(r"""
## 8. HX Importance Ranking (Impact on CIT)

Feature importances from the best tree-based model (Random Forest or
XGBoost), summed per HX across its `eps` / `dT_cold` / `dT_hot` / `duty_kW`
features, rank which exchangers matter most to CIT.
"""))
cells.append(code_cell(r"""
tree_models = {k: v for k, v in fitted.items() if hasattr(v, 'feature_importances_')}
importance_source = max(tree_models, key=lambda k: results_df.set_index('model').loc[k, 'within_10C_%'])
importances = pd.Series(fitted[importance_source].feature_importances_, index=X.columns).sort_values(ascending=False)

print(f'Using {importance_source} feature importances')
importances.head(15)
"""))

cells.append(code_cell(r"""
hx_importance = {}
for hx in HX_CONFIG.keys():
    cols = [c for c in X.columns if c.startswith(hx + '_')]
    if cols:
        hx_importance[hx] = importances[cols].sum()

hx_importance_s = pd.Series(hx_importance).sort_values(ascending=False)

fig, ax = plt.subplots(figsize=(9, 6))
ax.barh(hx_importance_s.index, hx_importance_s.values, color='tab:purple')
ax.set_xlabel(f'Aggregated {importance_source} feature importance')
ax.set_title('HX Importance to CIT Prediction')
ax.invert_yaxis()
plt.tight_layout()
plt.savefig(FIG_DIR / 'hx_importance_ranking.png', dpi=110, bbox_inches='tight')
plt.show()
hx_importance_s
"""))

# ── CELL: COMBINED PRIORITY ─────────────────────────────────────────────────
cells.append(md_cell(r"""
## 9. Combined HX Cleaning-Priority Table

Per the Cleaning & Problem Control Plan's Cleaning Priority Index concept
(`CPI ~ marginal CIT gain x ...`), the two rankings above are combined into a
single priority score (min-max normalized, equal weight, since real cleaning
cost/downtime numbers are not yet available -- see Section 10 limitations):

`priority = normalize(|fouling_rate|) + normalize(CIT_importance)`
"""))
cells.append(code_cell(r"""
def minmax(s):
    return (s - s.min()) / (s.max() - s.min()) if s.max() > s.min() else s * 0

fr = fouling_rank.set_index('HX')['median_fouling_rate_eps_per_day'].abs()
ci = hx_importance_s.reindex(fr.index).fillna(0)

priority = pd.DataFrame({
    'fouling_rate_abs': fr,
    'cit_importance': ci,
    'priority_score': minmax(fr) + minmax(ci),
}).sort_values('priority_score', ascending=False)

priority = priority.join(cleaning_reco.set_index('HX')[['recommended_action', 'drop_from_baseline_%']])
priority.to_csv(OUT_DIR / 'hx_cleaning_priority.csv')
print('Saved to', OUT_DIR / 'hx_cleaning_priority.csv')
priority
"""))

cells.append(code_cell(r"""
fig, ax = plt.subplots(figsize=(9, 6))
ax.barh(priority.index, priority['priority_score'], color='tab:red')
ax.set_xlabel('Combined priority score (fouling rate + CIT importance, normalized)')
ax.set_title('HX Cleaning Priority Ranking')
ax.invert_yaxis()
plt.tight_layout()
plt.savefig(FIG_DIR / 'hx_cleaning_priority.png', dpi=110, bbox_inches='tight')
plt.show()
"""))

# ── CELL: SUMMARY ────────────────────────────────────────────────────────────
cells.append(md_cell(r"""
## 10. Summary & Limitations

**What this notebook delivers:**
- Per-HX thermal effectiveness, dT, and duty trends from real 2024-2026 data
- Inferred fouling campaigns per HX (no maintenance log exists, so cleaning
  events are inferred from effectiveness step-changes)
- A fouling-rate ranking and a CIT-importance ranking, combined into a single
  cleaning-priority table with recommended-action dates
- A leak-free CIT prediction model comparison across 6 model families

**Known data limitations (carried over from
`CIT_Model_Dashboard_Solution_Design.docx` / `CPHT_Cleaning_and_Problem_Control_Plan.docx`):**
- True fouling resistance `Rf` (Eq. 13) needs exchanger area `A` and clean-`U`
  per shell; only one of sixteen HX (E107AB) has a datasheet value on hand, so
  this notebook uses thermal **effectiveness** as the fouling proxy instead of
  absolute `Rf`.
- `cp = 2.2 kJ/kg.K`, `rho = 850 kg/m3` are assumed constants, not derived
  from real crude assay (API/SG by blend) -- duty (`_duty_kW`) values are
  therefore directional, not absolute.
- No real cleaning/maintenance log exists to validate the inferred campaign
  boundaries -- engineer confirmation of inferred clean dates is recommended
  before acting on the priority table.
- E113A's hot-side residue temperatures (`1TI117.pv` in particular) show
  implausible swings in places, consistent with the "verify suspect tags"
  caveat in the reference docs; `E113A_dT_hot` / duty should be treated as
  indicative only.
- Cleaning cost, downtime, and fuel-price numbers (needed for a full CPI /
  economic cleaning point) are not yet available, so the combined priority
  score above only uses fouling rate + CIT importance, not economics.
"""))

# ── NOTEBOOK METADATA ────────────────────────────────────────────────────────
nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.13.0"}
    },
    "cells": cells
}

out = Path(__file__).parent / '5_HX_fouling_CIT_ranking.ipynb'
with open(out, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f'Notebook written to: {out}')
print(f'Total cells: {len(cells)}')
