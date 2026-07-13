"""
Helper script: builds 2_Feature_calculation.ipynb from cell definitions.
Run once: python _build_feature_calculation_notebook.py
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
# Feature Calculation — Crude Duty, Fouling, Combustion & NOx

**Input:** `Process_information_with_crude.csv` (cleaned process data + crude assay
properties, built in `1_cleaning_data_process.ipynb`)

Sections:
1. Load data
2. Crude cold-side duty per HX (Cp — Watson & Nelson, Density — ASTM D1250 Rackett)
3. Fouling indicators (effectiveness, LMTD/F, lumped UA, fouling-resistance proxy)
4. Furnace duty & combustion (excess air from flue-gas O2)
5. NOx @ reference O2 (guarded — only if a NOx tag exists in the dataset)
6. Assemble & export feature table
7. Validation / sanity checks

Reference: `Equations_Reference_Fouling_Combustion_NOx.docx` (Eq. 1–28, C1–C8, D1–D3)
and the crude cold-side duty formulas (Watson & Nelson Cp, ASTM D1250 Rackett density).
"""))

cells.append(code_cell("""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os

%matplotlib inline
plt.rcParams['figure.dpi'] = 100
plt.rcParams['font.size'] = 10

FIG_DIR = r'C:\\Desktop\\Bangchak Internship 2026\\furnace-optimization\\figures\\features'
os.makedirs(FIG_DIR, exist_ok=True)
"""))

cells.append(md_cell("""
---
## 1. Load Data
"""))

cells.append(code_cell("""
FILEPATH = r'C:\\Desktop\\Bangchak Internship 2026\\Data\\Process_information_with_crude.csv'

df = pd.read_csv(FILEPATH, index_col=0, parse_dates=True)

print(f'Shape: {df.shape}')
print(f'Date range: {df.index.min().date()} to {df.index.max().date()}')
df.head()
"""))

cells.append(md_cell("""
---
## 2. Crude Cold-Side Duty per Heat Exchanger

**Formulas (cold side = crude):**

- `T_avg = (T_c_in + T_c_out) / 2`
- `Cp = (1.685 + 0.00339*T_avg) / sqrt(SG)`  — Watson & Nelson, kJ/kg·°C
- `ρ15.6 = SG * 999.016`
- `α = 613.9723 / ρ15.6**2`
- `ρ(T) = ρ15.6 * exp(-α*(T_avg-15.6)*(1 + 0.8*α*(T_avg-15.6)))`  — ASTM D1250 Rackett, kg/m³
- `ṁ = Flow(m3/h) * ρ(T) / 3600`  — kg/s
- `Q = ṁ * Cp * (T_c_out - T_c_in)`  — kW

`HX_CONFIG` below mirrors the heat-exchanger breakdown defined in
`1_cleaning_data_process.ipynb` (cold = crude side, hot = side-run/kero/GO/residue).
Several HXs share their crude flow meter with an upstream unit in the same train
(crude doesn't get re-metered between chained exchangers) — noted as `flow_source`.
"""))

cells.append(code_cell("""
HX_CONFIG = {
    'E101AB':  {'cold_flow': '1FI007.pv', 'cold_in': '1TI102.pv', 'cold_out': '1TI101.pv',
                'hot_in': '1TI194.pv', 'hot_out': '1TI103.pv'},
    'E101CD':  {'cold_flow': '1FI008.pv', 'cold_in': '1TI102.pv', 'cold_out': '1TI104.pv',
                'hot_in': '1TI194.pv', 'hot_out': '1TI105.pv'},
    'E101EF':  {'cold_flow': '1FI009.pv', 'cold_in': '1TI102.pv', 'cold_out': '1TI109.pv',
                'hot_in': '1TI194.pv', 'hot_out': '1TI110.pv'},
    'E102':    {'cold_flow': '1fi005.pv', 'cold_in': '1TI107.pv', 'cold_out': '1TI106.pv',
                'hot_in': '1TI165.pv', 'hot_out': '1TI108.pv', 'flow_source': 'total charge (no dedicated meter)'},
    'E103AB':  {'cold_flow': '1FI015.pv', 'cold_in': '1TI225.pv', 'cold_out': '1TI136.pv',
                'hot_in': '4TI107.pv', 'hot_out': '1TI137.pv'},
    'E104':    {'cold_flow': '1FI015.pv', 'cold_in': '1TI136.pv', 'cold_out': '1TI112.pv',
                'hot_in': '1TI195.pv', 'hot_out': '4TI115.pv', 'flow_source': 'shared with E103AB (same crude stream)'},
    'E105AB':  {'cold_flow': '1FI015.pv', 'cold_in': '1TI112.pv', 'cold_out': '1TI114.pv',
                'hot_in': '1ti196.pv', 'hot_out': '1TI113.pv', 'flow_source': 'shared with E103AB (same crude stream)'},
    'E106AB':  {'cold_flow': '1FI016.pv', 'cold_in': '1TI225.pv', 'cold_out': '1TI128.pv',
                'hot_in': '4TI107.pv', 'hot_out': '1TI129.pv'},
    'E107AB':  {'cold_flow': '1FI016.pv', 'cold_in': '1TI128.pv', 'cold_out': '1TI130.pv',
                'hot_in': '1TI135.pv', 'hot_out': '1TI131.pv', 'flow_source': 'shared with E106AB (same crude stream)'},
    'E108AB':  {'cold_flow': '1FI016.pv', 'cold_in': '1TI130.pv', 'cold_out': '1TI132.pv',
                'hot_in': '1TI127.pv', 'hot_out': '1TI133.pv', 'flow_source': 'shared with E106AB (same crude stream)'},
    'E109AB':  {'cold_flow': '1FI016.pv', 'cold_in': '1TI132.pv', 'cold_out': '1TI134.pv',
                'hot_in': '1TI163.pv', 'hot_out': '1TI135.pv', 'flow_source': 'shared with E106AB (same crude stream)'},
    'E110ABC': {'cold_flow': '1FI017.pv', 'cold_in': '1TI225.pv', 'cold_out': '1TI124.pv',
                'hot_in': '1TI133.pv', 'hot_out': '1TI122.pv'},
    'E111':    {'cold_flow': '1FI017.pv', 'cold_in': '1TI124.pv', 'cold_out': '1TI123.pv',
                'hot_in': '1TI113.pv', 'hot_out': '1TI125.pv', 'flow_source': 'shared with E110ABC (same crude stream)'},
    'E112AB':  {'cold_flow': '1FI017.pv', 'cold_in': '1TI123.pv', 'cold_out': '1TI126.pv',
                'hot_in': '1TI117.pv', 'hot_out': '1TI127.pv', 'flow_source': 'shared with E110ABC (same crude stream)'},
    'E112C':   {'cold_flow': '1FI017.pv', 'cold_in': '1TI123.pv', 'cold_out': '1TI114.pv',
                'hot_in': '1TI117.pv', 'hot_out': '1TI117B.pv', 'flow_source': 'shared with E110ABC (same crude stream)'},
    'E113A':   {'cold_flow': '1fi005.pv', 'cold_in': '1TI115.pv', 'cold_out': '1TI116.pv',
                'hot_in': '1TI161.pv', 'hot_out': '1TI117.pv', 'flow_source': 'total charge (no dedicated meter)'},
}

for hx, cfg in HX_CONFIG.items():
    missing = [t for t in [cfg['cold_flow'], cfg['cold_in'], cfg['cold_out']] if t not in df.columns]
    if missing:
        print(f'{hx}: MISSING tags {missing}')

print(f'\\nDefined {len(HX_CONFIG)} heat exchangers for crude-side duty calculation')
"""))

cells.append(md_cell("### 2.1 Compute Cp, Density, Mass Flow, Duty (Q) per HX"))

cells.append(code_cell("""
SG = df['SG_15_6C']

duty_results = {}

for hx, cfg in HX_CONFIG.items():
    flow_m3h = df[cfg['cold_flow']]
    t_in = df[cfg['cold_in']]
    t_out = df[cfg['cold_out']]

    t_avg = (t_in + t_out) / 2
    cp = ((1.685 + 0.00339 * t_avg) / np.sqrt(SG)).round(2)

    rho_156 = SG * 999.016
    alpha = 613.9723 / rho_156**2
    rho_t = (rho_156 * np.exp(-alpha * (t_avg - 15.6) * (1 + 0.8 * alpha * (t_avg - 15.6)))).round(0)

    mdot = flow_m3h * rho_t / 3600
    q = mdot * cp * (t_out - t_in)

    duty_results[hx] = pd.DataFrame({
        f'{hx}_Tavg': t_avg,
        f'{hx}_Cp': cp,
        f'{hx}_density': rho_t,
        f'{hx}_mdot': mdot,
        f'{hx}_Q': q,
    })

duty_df = pd.concat(duty_results.values(), axis=1)
print(f'Duty columns added: {duty_df.shape[1]} ({len(HX_CONFIG)} HX x 5 metrics)')
duty_df[[f'{hx}_Q' for hx in HX_CONFIG]].describe().T[['mean', 'std', 'min', 'max']].round(1)
"""))

cells.append(md_cell("### 2.2 Duty Time-Series per HX"))

cells.append(code_cell("""
fig, ax = plt.subplots(figsize=(16, 6))
colors = plt.cm.tab20(np.linspace(0, 1, len(HX_CONFIG)))

for (hx, _), color in zip(HX_CONFIG.items(), colors):
    ax.plot(duty_df.index, duty_df[f'{hx}_Q'], label=hx, color=color, linewidth=0.8, alpha=0.85)

ax.set_ylabel('Q (kW)')
ax.set_xlabel('Date')
ax.set_title('Crude Cold-Side Duty per Heat Exchanger')
ax.legend(fontsize=7, ncol=4, loc='upper right')
ax.grid(True, alpha=0.3)
plt.tight_layout()
fig.savefig(os.path.join(FIG_DIR, 'duty_per_hx.png'), dpi=150, bbox_inches='tight')
plt.show()
"""))

cells.append(md_cell("""
---
## 3. Fouling Indicators

**Limitation:** No heat-transfer area (A) or design U-value tags are available
in `Tag Process.xlsx`, so absolute fouling resistance `Rf [m2*K/W]` (Eq. 13)
cannot be computed directly. Instead we compute a **lumped UA proxy**
(`UA = Q / (F * LMTD)`, units kW/°C) and derive a fouling-resistance *proxy*
(`Rf_proxy = 1/UA_fouling - 1/UA_clean_baseline`) — this tracks fouling buildup
and recovery (cleaning events) correctly, but is not normalized by area, so it
is **not directly comparable in absolute m2*K/W units** across HXs of different
size. If a design data sheet with `A` per HX becomes available, divide by `A`
to get true `Rf`.

Effectiveness `ε = (T_H,in - T_H,out) / (T_H,in - T_C,in)` (Eq. 9) only needs
temperatures, so it is exact (assumes hot side ~ Cmin, a standard simplification
when the crude/cold-side flow is design-larger than the hot side).
"""))

cells.append(code_cell("""
fouling_results = {}

for hx, cfg in HX_CONFIG.items():
    t_ci = df[cfg['cold_in']]
    t_co = df[cfg['cold_out']]
    t_hi = df[cfg['hot_in']]
    t_ho = df[cfg['hot_out']]
    q = duty_df[f'{hx}_Q']

    # Effectiveness (Eq. 9)
    eps = (t_hi - t_ho) / (t_hi - t_ci)

    # LMTD (Eq. 11) - counter-current
    dt1 = t_hi - t_co
    dt2 = t_ho - t_ci
    with np.errstate(divide='ignore', invalid='ignore'):
        lmtd = (dt1 - dt2) / np.log(dt1 / dt2)
    lmtd = lmtd.where((dt1 > 0) & (dt2 > 0) & (dt1 != dt2), other=(dt1 + dt2) / 2)

    # F-factor (Eq. 23-25)
    R = (t_hi - t_ho) / (t_co - t_ci)
    S = (t_co - t_ci) / (t_hi - t_ci)
    sqrt_term = np.sqrt(R**2 + 1)
    num = sqrt_term * np.log((1 - S).clip(lower=1e-6) / (1 - R * S).clip(lower=1e-6))
    den_inner_num = 2 - S * (R + 1 - sqrt_term)
    den_inner_den = 2 - S * (R + 1 + sqrt_term)
    den = (R - 1) * np.log(den_inner_num.clip(lower=1e-6) / den_inner_den.clip(lower=1e-6))
    f_factor = (num / den).clip(lower=0.5, upper=1.0)
    f_factor = f_factor.fillna(1.0)

    # Lumped UA (Eq. 12 rearranged, no area): UA = Q / (F * LMTD)
    ua = q / (f_factor * lmtd)
    ua = ua.where(lmtd.abs() > 0.1)

    # Clean baseline = rolling 90-day max UA (fouling only reduces UA between cleanings)
    ua_clean = ua.rolling(window=90, min_periods=10, center=False).max().bfill()

    rf_proxy = (1 / ua - 1 / ua_clean)

    fouling_results[hx] = pd.DataFrame({
        f'{hx}_effectiveness': eps.clip(0, 1),
        f'{hx}_LMTD': lmtd,
        f'{hx}_F': f_factor,
        f'{hx}_UA': ua,
        f'{hx}_Rf_proxy': rf_proxy,
    })

fouling_df = pd.concat(fouling_results.values(), axis=1)
print(f'Fouling columns added: {fouling_df.shape[1]}')
fouling_df[[f'{hx}_effectiveness' for hx in HX_CONFIG]].describe().T[['mean', 'std', 'min', 'max']].round(3)
"""))

cells.append(md_cell("### 3.1 Fouling Resistance Proxy — Sawtooth Check (top 3 lowest-effectiveness HX)"))

cells.append(code_cell("""
worst_hx = fouling_df[[f'{hx}_effectiveness' for hx in HX_CONFIG]].mean().sort_values().index[:3]
worst_hx = [c.replace('_effectiveness', '') for c in worst_hx]

fig, axes = plt.subplots(len(worst_hx), 1, figsize=(16, 3.2 * len(worst_hx)), sharex=True)
for ax, hx in zip(axes, worst_hx):
    ax.plot(fouling_df.index, fouling_df[f'{hx}_Rf_proxy'], color='#d62728', linewidth=0.9)
    ax.set_ylabel('Rf proxy')
    ax.set_title(f'{hx} — Fouling Resistance Proxy (lowest mean effectiveness)', fontsize=10, loc='left')
    ax.grid(True, alpha=0.3)
axes[-1].set_xlabel('Date')
plt.tight_layout()
fig.savefig(os.path.join(FIG_DIR, 'fouling_proxy_worst3.png'), dpi=150, bbox_inches='tight')
plt.show()
"""))

cells.append(md_cell("""
---
## 4. Furnace Duty & Combustion

- `Q_furnace = ṁ_crude * Cp * (COT - CIT)` using the same Watson & Nelson / Rackett
  formulas as Section 2, with total charge flow (`1fi005.pv`).
- Excess air from measured flue-gas O2 (`1AI001.pv`), Eq. C6-C7:
  `EA = O2 / (20.9 - O2)`, `lambda = 20.9 / (20.9 - O2)`.
- Stoichiometric air/fuel ratio (Eq. C1-C5) needs fuel-gas composition, which is
  not available as a DCS tag — left out (documented gap).
"""))

cells.append(code_cell("""
CIT_TAG, COT_TAG, TOTAL_FLOW_TAG, O2_TAG = '1TI116.pv', '1TC007.pv', '1fi005.pv', '1AI001.pv'

cit, cot = df[CIT_TAG], df[COT_TAG]
t_avg_furnace = (cit + cot) / 2
cp_furnace = (1.685 + 0.00339 * t_avg_furnace) / np.sqrt(SG)
rho_156 = SG * 999.016
alpha = 613.9723 / rho_156**2
rho_furnace = rho_156 * np.exp(-alpha * (t_avg_furnace - 15.6) * (1 + 0.8 * alpha * (t_avg_furnace - 15.6)))
mdot_furnace = df[TOTAL_FLOW_TAG] * rho_furnace / 3600
q_furnace = mdot_furnace * cp_furnace * (cot - cit)

o2 = df[O2_TAG]
excess_air_frac = o2 / (20.9 - o2)
lambda_ratio = 20.9 / (20.9 - o2)

combustion_df = pd.DataFrame({
    'Q_furnace_kW': q_furnace,
    'excess_air_frac': excess_air_frac,
    'lambda_excess_air_ratio': lambda_ratio,
})

print(combustion_df.describe().round(3))

fig, axes = plt.subplots(2, 1, figsize=(16, 7), sharex=True)
axes[0].plot(combustion_df.index, combustion_df['Q_furnace_kW'], color='#e6550d', linewidth=0.9)
axes[0].set_ylabel('kW')
axes[0].set_title('Furnace Duty (Q_furnace)', loc='left')
axes[0].grid(True, alpha=0.3)

axes[1].plot(combustion_df.index, combustion_df['excess_air_frac'] * 100, color='#756bb1', linewidth=0.9)
axes[1].set_ylabel('Excess air %')
axes[1].set_title('Excess Air from Flue-Gas O2 (1AI001.pv)', loc='left')
axes[1].grid(True, alpha=0.3)
axes[-1].set_xlabel('Date')
plt.tight_layout()
fig.savefig(os.path.join(FIG_DIR, 'furnace_duty_combustion.png'), dpi=150, bbox_inches='tight')
plt.show()
"""))

cells.append(md_cell("""
---
## 5. NOx @ Reference O2 (Eq. D1-D2)

`NOx_at_ref = NOx_measured * (20.9 - O2_ref) / (20.9 - O2_measured)`, with
`O2_ref = 3%` (typical Thai PCD reference basis for gas-fired process heaters).

This section only runs if a NOx DCS tag is present in the dataset — searched
in `Tag Process.xlsx` and the cleaned process columns, **none was found**, so
it is skipped with a clear message rather than fabricating values.
"""))

cells.append(code_cell("""
NOX_TAG_CANDIDATES = [c for c in df.columns if 'nox' in c.lower() or 'no x' in c.lower()]
O2_REF = 3.0

if NOX_TAG_CANDIDATES:
    nox_tag = NOX_TAG_CANDIDATES[0]
    nox_meas = df[nox_tag]
    nox_at_ref = nox_meas * (20.9 - O2_REF) / (20.9 - o2)
    nox_df = pd.DataFrame({'NOx_measured_ppm': nox_meas, 'NOx_at_ref3pct_ppm': nox_at_ref})
    print(f'NOx tag found: {nox_tag}')
    print(nox_df.describe().round(1))
else:
    nox_df = pd.DataFrame(index=df.index)
    print('NOx tag NOT available in current dataset (checked Tag Process.xlsx and process columns).')
    print('Section D skipped. Add a NOx DCS tag to enable this calculation.')
"""))

cells.append(md_cell("""
---
## 6. Assemble & Export Feature Table
"""))

cells.append(code_cell("""
feature_df = pd.concat([df, duty_df, fouling_df, combustion_df, nox_df], axis=1)

OUTPUT_PATH = r'C:\\Desktop\\Bangchak Internship 2026\\Data\\Feature_calculated.csv'
feature_df.to_csv(OUTPUT_PATH)

print(f'Saved to: {OUTPUT_PATH}')
print(f'Shape: {feature_df.shape}')
print(f'Added columns: {feature_df.shape[1] - df.shape[1]}')
"""))

cells.append(md_cell("""
---
## 7. Validation / Sanity Checks
"""))

cells.append(code_cell("""
print('='*60)
print('         FEATURE CALCULATION SUMMARY')
print('='*60)

cp_cols = [f'{hx}_Cp' for hx in HX_CONFIG]
dens_cols = [f'{hx}_density' for hx in HX_CONFIG]
eps_cols = [f'{hx}_effectiveness' for hx in HX_CONFIG]
rf_cols = [f'{hx}_Rf_proxy' for hx in HX_CONFIG]

cp_all = feature_df[cp_cols].stack()
dens_all = feature_df[dens_cols].stack()
eps_all = feature_df[eps_cols].stack()
rf_all = feature_df[rf_cols].stack()

print(f'Cp range:            {cp_all.min():.2f} - {cp_all.max():.2f} kJ/kg.C  '
      f'(expected ~1.9-2.4)')
print(f'Density range:       {dens_all.min():.0f} - {dens_all.max():.0f} kg/m3  '
      f'(expected ~750-870)')
print(f'Effectiveness range: {eps_all.min():.3f} - {eps_all.max():.3f}  '
      f'(must be within [0, 1] by construction - clipped)')
print(f'Rf_proxy >= 0 frac:  {(rf_all >= 0).mean()*100:.1f}%  '
      f'(should be mostly >=0; negative values indicate measurement noise or a cleaning event)')
print(f'Q_furnace mean:      {feature_df[\"Q_furnace_kW\"].mean():.0f} kW')
print('='*60)
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

out_path = Path(__file__).parent / "2_Feature_calculation.ipynb"
out_path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {out_path}")
