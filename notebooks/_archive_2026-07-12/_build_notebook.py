"""
Helper script: builds 1_EDA_standard_sheet.ipynb from cell definitions.
Run once: python _build_notebook.py
"""
import json, textwrap
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

# ────────────────────────────────────────────────────────────────────────────
cells = []

# ── TITLE ───────────────────────────────────────────────────────────────────
cells.append(md_cell("""
# EDA — Standard Sheet Process Information Data
**Bangchak Plant 3 TPU | CIT Optimization Project**

Data range: 2024-01-01 → 2026-06-02 (~884 daily observations, 104 PI tags)

Sections:
1. Load & parse data
2. Data overview & missing values
3. Time-series — CIT & key temperatures
4. Crude charge rate & flow trends
5. CPHT temperature profile (per train)
6. Correlation heatmap
7. Scatter plots — CIT vs key variables
8. Furnace radiant tube temps (TMT 1TI139–1TI152)
9. Distribution plots (histograms + box plots)
10. Rolling statistics — fouling trend proxy
"""))

# ── CELL 1: IMPORTS ─────────────────────────────────────────────────────────
cells.append(code_cell("""
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from pathlib import Path

plt.rcParams.update({'figure.dpi': 120, 'font.size': 11,
                     'axes.grid': True, 'grid.alpha': 0.3})
sns.set_palette('tab10')

DATA_PATH = Path(r'C:\\\\Desktop\\\\Bangchak Internship 2026\\\\Data')
FILE = DATA_PATH / 'Standard Sheet - Process information data 4.xlsx'
print('File exists:', FILE.exists())
"""))

# ── CELL 2: LOAD ─────────────────────────────────────────────────────────────
cells.append(md_cell("## 1. Load & Parse Data"))
cells.append(code_cell("""
raw = pd.read_excel(FILE, header=None)

tags      = raw.iloc[3, 3:].values
units_row = raw.iloc[4, 3:].values
desc_row  = raw.iloc[5, 3:].values

columns_config = []
for tag, unit, desc in zip(tags, units_row, desc_row):
    columns_config.append({
        'tag': str(tag),
        'unit': str(unit) if pd.notna(unit) else '',
        'description': str(desc) if pd.notna(desc) else '',
    })

df = raw.iloc[7:, 2:].copy()
df.columns = ['Timestamp'] + [c['tag'] for c in columns_config]
df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
df = df.dropna(subset=['Timestamp']).sort_values('Timestamp').reset_index(drop=True)

tag_cols = [c['tag'] for c in columns_config]
df[tag_cols] = df[tag_cols].apply(pd.to_numeric, errors='coerce')

tag_to_desc = {c['tag']: c['description'] for c in columns_config}
tag_to_unit = {c['tag']: c['unit'] for c in columns_config}

print(f'Shape: {df.shape}')
print(f'Date range: {df.Timestamp.min().date()} -> {df.Timestamp.max().date()}')
print(f'Columns: {len(tag_cols)} tags')
df.head(3)
"""))

# ── CELL 3: OVERVIEW ─────────────────────────────────────────────────────────
cells.append(md_cell("## 2. Data Overview & Missing Values"))
cells.append(code_cell("""
summary = df[tag_cols].describe().T
summary['missing_%'] = df[tag_cols].isna().mean() * 100
summary['missing_%'] = summary['missing_%'].round(1)
print(summary[['count','mean','std','min','max','missing_%']].to_string())
"""))

cells.append(code_cell("""
missing = df[tag_cols].isna().mean() * 100
missing_tags = missing[missing > 0].sort_values(ascending=False)

if len(missing_tags) > 0:
    fig, ax = plt.subplots(figsize=(10, max(4, len(missing_tags) * 0.3)))
    missing_tags.plot(kind='barh', ax=ax, color='salmon')
    ax.set_xlabel('Missing (%)')
    ax.set_title('Tags with Missing Values')
    plt.tight_layout()
    plt.show()
else:
    print('No missing values — dataset is complete.')
"""))

# ── CELL 4: CIT TIME SERIES ──────────────────────────────────────────────────
cells.append(md_cell("""
## 3. Time-Series — CIT & Key Temperatures

Key tags:
- **1TI116** = CIT (Crude Inlet Temperature to furnace F101) <- main target
- **1TI106** = CPHT-1 outlet
- **1TI105** = CPHT-2 inlet
- **1TI101–1TI105** = preheat train temperatures
"""))
cells.append(code_cell("""
fig, ax = plt.subplots(figsize=(14, 4))
if '1TI116.pv' in df.columns:
    ax.plot(df.Timestamp, df['1TI116.pv'], lw=1.2, color='tab:red', label='CIT (1TI116)')
    ax.axhline(df['1TI116.pv'].mean(), color='gray', ls='--', lw=1, label=f'Mean = {df["1TI116.pv"].mean():.1f} C')
    ax.set_ylabel('Temperature (C)')
    ax.set_title('CIT (1TI116) - Daily Average | 2024-2026')
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    plt.xticks(rotation=30)
plt.tight_layout()
plt.show()
"""))

cells.append(code_cell("""
ti_cols = ['1TI101.pv','1TI102.pv','1TI103.pv','1TI104.pv','1TI105.pv',
           '1TI106.pv','1TI116.pv']
ti_labels = ['1TI101','1TI102','1TI103','1TI104','1TI105','1TI106 (CPHT-1 out)','1TI116 (CIT)']

valid = [(c,l) for c,l in zip(ti_cols, ti_labels) if c in df.columns]

fig, ax = plt.subplots(figsize=(14, 5))
for col, label in valid:
    ax.plot(df.Timestamp, df[col], lw=1, label=label, alpha=0.85)
ax.set_ylabel('Temperature (C)')
ax.set_title('CPHT Preheat Train Temperatures Over Time')
ax.legend(loc='upper left', fontsize=9)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
plt.xticks(rotation=30)
plt.tight_layout()
plt.show()
"""))

# ── CELL 5: CHARGE RATE ──────────────────────────────────────────────────────
cells.append(md_cell("""
## 4. Crude Charge Rate & Flow Trends

- **1FC001 + 1FC002** = Total crude charge (m3/hr)
- **1FC020-1FC023** = Crude to furnace passes
- **1AI001** = Flue gas O2 (%)
"""))
cells.append(code_cell("""
fig, axes = plt.subplots(2, 1, figsize=(14, 7), sharex=True)

charge_cols = ['1FC001.pv', '1FC002.pv']
valid_charge = [c for c in charge_cols if c in df.columns]
if valid_charge:
    df['total_charge'] = df[valid_charge].sum(axis=1)
    axes[0].plot(df.Timestamp, df['total_charge'], color='steelblue', lw=1.2)
    axes[0].set_ylabel('Flow (m3/hr)')
    axes[0].set_title('Total Crude Charge Rate (1FC001 + 1FC002)')

if '1AI001.pv' in df.columns:
    axes[1].plot(df.Timestamp, df['1AI001.pv'], color='darkorange', lw=1.2)
    axes[1].axhline(2.0, color='red', ls='--', lw=1, label='Min O2 = 2%')
    axes[1].axhline(3.0, color='green', ls='--', lw=1, label='Target O2 = 3%')
    axes[1].set_ylabel('O2 (%)')
    axes[1].set_title('Flue Gas O2 (1AI001)')
    axes[1].legend()

axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
plt.xticks(rotation=30)
plt.tight_layout()
plt.show()
"""))

cells.append(code_cell("""
pass_cols = ['1FC020.pv','1FC021.pv','1FC022.pv','1FC023.pv']
valid_pass = [c for c in pass_cols if c in df.columns]

if valid_pass:
    fig, ax = plt.subplots(figsize=(14, 4))
    for c in valid_pass:
        ax.plot(df.Timestamp, df[c], lw=1, label=c.replace('.pv',''), alpha=0.8)
    ax.set_ylabel('Flow (m3/hr)')
    ax.set_title('Crude to F101 - Pass Flows (1FC020-1FC023)')
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    plt.xticks(rotation=30)
    plt.tight_layout()
    plt.show()
"""))

# ── CELL 6: CPHT PROFILE ────────────────────────────────────────────────────
cells.append(md_cell("""
## 5. CPHT Temperature Profile (Train-Level)

Average temperature at each exchanger stage — snapshot of the preheat train shape.
"""))
cells.append(code_cell("""
preheat_order = [
    '1TI102.pv','1TI101.pv','1TI104.pv','1TI109.pv',
    '1TI106.pv','1TI107.pv','1TI108.pv','1TI110.pv',
    '1TI112.pv','1TI113.pv','1TI114.pv','1TI115.pv','1TI116.pv'
]
valid_ph = [c for c in preheat_order if c in df.columns]

if valid_ph:
    means = df[valid_ph].mean()
    stds  = df[valid_ph].std()
    labels = [c.replace('.pv','') for c in valid_ph]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.errorbar(range(len(valid_ph)), means.values, yerr=stds.values,
                fmt='o-', capsize=4, color='tab:blue', lw=2, label='Mean +/- 1 std')
    if '1TI116.pv' in valid_ph:
        idx = valid_ph.index('1TI116.pv')
        ax.scatter([idx], [means['1TI116.pv']], color='red', zorder=5, s=100, label='CIT (1TI116)')

    ax.set_xticks(range(len(valid_ph)))
    ax.set_xticklabels(labels, rotation=45, ha='right')
    ax.set_ylabel('Temperature (C)')
    ax.set_title('Average Temperature Profile Along Preheat Train (2024-2026)')
    ax.legend()
    plt.tight_layout()
    plt.show()
"""))

# ── CELL 7: CORRELATION HEATMAP ─────────────────────────────────────────────
cells.append(md_cell("""
## 6. Correlation Heatmap

Pearson correlation between all numeric tags. Focus on columns correlated with **1TI116 (CIT)**.
"""))
cells.append(code_cell("""
temp_tags = [c for c in tag_cols if c.startswith('1TI') or c.startswith('1TC')]
temp_tags = [c for c in temp_tags if c in df.columns]

corr = df[temp_tags].corr()

fig, ax = plt.subplots(figsize=(18, 16))
mask = np.triu(np.ones_like(corr, dtype=bool))
sns.heatmap(corr, mask=mask, annot=False, fmt='.2f', cmap='RdYlGn',
            vmin=-1, vmax=1, ax=ax, linewidths=0.3,
            cbar_kws={'shrink': 0.7})
ax.set_title('Correlation Matrix - Temperature Tags (1TI*/1TC*)')
plt.tight_layout()
plt.show()
"""))

cells.append(code_cell("""
target = '1TI116.pv'
if target in df.columns:
    corr_cit = df[tag_cols].corrwith(df[target]).dropna().sort_values(key=abs, ascending=False)
    corr_cit = corr_cit[corr_cit.index != target]

    fig, ax = plt.subplots(figsize=(10, 8))
    colors = ['tab:green' if v > 0 else 'tab:red' for v in corr_cit.values]
    corr_cit.plot(kind='barh', ax=ax, color=colors)
    ax.axvline(0, color='black', lw=0.8)
    ax.set_xlabel('Pearson r')
    ax.set_title('Correlation of All Tags with CIT (1TI116)')
    plt.tight_layout()
    plt.show()
    print('\\nTop 15 positively correlated:')
    print(corr_cit.head(15).to_string())
    print('\\nTop 5 negatively correlated:')
    print(corr_cit.tail(5).to_string())
"""))

# ── CELL 8: SCATTER PLOTS ───────────────────────────────────────────────────
cells.append(md_cell("""
## 7. Scatter Plots — CIT vs Key Variables

Color-coded by year to visualize drift over time.
"""))
cells.append(code_cell("""
target = '1TI116.pv'
if target in df.columns:
    top_tags = [c for c in corr_cit.head(8).index if c != target and c in df.columns][:6]

    extra = ['1FC001.pv', '1AI001.pv']
    scatter_vars = top_tags + [e for e in extra if e in df.columns and e not in top_tags]

    df['year'] = df.Timestamp.dt.year
    palette = {y: c for y, c in zip(sorted(df.year.unique()), ['tab:blue','tab:orange','tab:green','tab:red'])}

    n = len(scatter_vars)
    ncols = 3
    nrows = (n + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(15, 4 * nrows))
    axes = axes.flatten()

    for i, var in enumerate(scatter_vars):
        ax = axes[i]
        for yr, color in palette.items():
            mask = df.year == yr
            ax.scatter(df.loc[mask, var], df.loc[mask, target],
                       alpha=0.4, s=15, color=color, label=str(yr))
        ax.set_xlabel(var.replace('.pv',''), fontsize=9)
        ax.set_ylabel('CIT (C)', fontsize=9)
        r = df[[var, target]].dropna().corr().iloc[0, 1]
        ax.set_title(f'{var.replace(".pv","")}  (r = {r:.2f})', fontsize=10)
        if i == 0:
            ax.legend(title='Year', fontsize=8, markerscale=1.5)

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    plt.suptitle('CIT (1TI116) vs Key Variables', fontsize=13, y=1.01)
    plt.tight_layout()
    plt.show()
"""))

# ── CELL 9: RADIANT TMT ─────────────────────────────────────────────────────
cells.append(md_cell("""
## 8. Furnace Radiant Tube Temperatures (TMT)

Tags: 1TI139-1TI152 (radiant section tube-skin thermocouples).
"""))
cells.append(code_cell("""
tmt_tags = [f'1TI{n}.pv' for n in range(139, 153)]
valid_tmt = [c for c in tmt_tags if c in df.columns]

if valid_tmt:
    fig, ax = plt.subplots(figsize=(14, 5))
    for col in valid_tmt:
        ax.plot(df.Timestamp, df[col], lw=0.9, alpha=0.75, label=col.replace('.pv',''))

    ax.set_ylabel('Tube Skin Temp (C)')
    ax.set_title('Radiant Tube Skin Temperatures (1TI139-1TI152)')
    ax.legend(loc='upper left', fontsize=8, ncol=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    plt.xticks(rotation=30)
    plt.tight_layout()
    plt.show()
else:
    print('TMT tags (1TI139-1TI152) not found in dataset.')
"""))

cells.append(code_cell("""
if valid_tmt:
    fig, ax = plt.subplots(figsize=(12, 5))
    data_box = [df[c].dropna().values for c in valid_tmt]
    labels_box = [c.replace('.pv','') for c in valid_tmt]
    bp = ax.boxplot(data_box, labels=labels_box, patch_artist=True,
                    boxprops=dict(facecolor='lightcoral', alpha=0.6))
    ax.set_ylabel('Temperature (C)')
    ax.set_title('TMT Distribution per Thermocouple')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()
"""))

# ── CELL 10: DISTRIBUTIONS ───────────────────────────────────────────────────
cells.append(md_cell("""
## 9. Distribution Plots — Key Tags

Histograms and KDE for the most process-critical variables.
"""))
cells.append(code_cell("""
key_tags_dist = {
    '1TI116.pv': 'CIT (C)',
    '1TI106.pv': 'CPHT-1 Outlet (C)',
    '1FC001.pv': 'Crude Charge-1 (m3/hr)',
    '1AI001.pv': 'Flue Gas O2 (%)',
    '1TC007.pv': '1TC007 (C)',
}
valid_key = {k: v for k, v in key_tags_dist.items() if k in df.columns}

ncols = 3
nrows = (len(valid_key) + ncols - 1) // ncols
fig, axes = plt.subplots(nrows, ncols, figsize=(14, 4 * nrows))
axes = axes.flatten()

for i, (col, label) in enumerate(valid_key.items()):
    ax = axes[i]
    vals = df[col].dropna()
    ax.hist(vals, bins=40, color='steelblue', alpha=0.5, density=True, label='Histogram')
    vals.plot.kde(ax=ax, color='navy', lw=2, label='KDE')
    ax.axvline(vals.mean(), color='red', ls='--', lw=1.2, label=f'Mean = {vals.mean():.1f}')
    ax.axvline(vals.median(), color='green', ls=':', lw=1.2, label=f'Median = {vals.median():.1f}')
    ax.set_xlabel(label)
    ax.set_title(f'Distribution: {col.replace(".pv","")}')
    ax.legend(fontsize=8)

for j in range(i + 1, len(axes)):
    axes[j].set_visible(False)

plt.tight_layout()
plt.show()
"""))

# ── CELL 11: ROLLING STATS ───────────────────────────────────────────────────
cells.append(md_cell("""
## 10. Rolling Statistics — Fouling Trend Proxy

A 30-day rolling mean of CIT shows the fouling degradation trend between cleaning events.
Sharp upward jumps = potential cleaning events (CIT recovery).
"""))
cells.append(code_cell("""
target = '1TI116.pv'
if target in df.columns:
    df_t = df.set_index('Timestamp')[target].dropna()

    roll_mean = df_t.rolling(window=30, min_periods=15).mean()
    roll_std  = df_t.rolling(window=30, min_periods=15).std()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7), sharex=True)

    ax1.plot(df_t.index, df_t.values, alpha=0.3, lw=0.8, color='gray', label='Daily CIT')
    ax1.plot(roll_mean.index, roll_mean.values, lw=2, color='tab:red', label='30-day rolling mean')
    ax1.fill_between(roll_mean.index,
                     roll_mean - roll_std, roll_mean + roll_std,
                     alpha=0.2, color='tab:red', label='+/-1 std band')
    ax1.set_ylabel('CIT (C)')
    ax1.set_title('CIT Rolling Mean - Fouling Degradation Trend')
    ax1.legend()

    ax2.plot(roll_std.index, roll_std.values, lw=1.5, color='tab:purple')
    ax2.set_ylabel('Rolling Std (C)')
    ax2.set_title('CIT 30-day Rolling Std (spikes may indicate cleaning events)')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

    plt.xticks(rotation=30)
    plt.tight_layout()
    plt.show()
"""))

cells.append(code_cell("""
target = '1TI116.pv'
if target in df.columns:
    df_t = df.set_index('Timestamp')[target].dropna()
    daily_diff = df_t.diff()

    THRESHOLD = 5.0

    fig, ax = plt.subplots(figsize=(14, 4))
    ax.bar(daily_diff.index, daily_diff.values,
           color=['tab:green' if v > THRESHOLD else ('salmon' if v < -2 else 'lightgray')
                  for v in daily_diff.values],
           width=1, alpha=0.8)
    ax.axhline(THRESHOLD,  color='green', ls='--', lw=1.2,
               label=f'Clean event threshold (+{THRESHOLD} C/day)')
    ax.axhline(-2, color='orange', ls='--', lw=1.2, label='-2 C/day (fouling signal)')
    ax.axhline(0, color='black', lw=0.6)
    ax.set_ylabel('delta CIT (C/day)')
    ax.set_title('Daily CIT Change - Cleaning Event Detection')
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    plt.xticks(rotation=30)
    plt.tight_layout()
    plt.show()

    clean_candidates = daily_diff[daily_diff > THRESHOLD]
    print(f'Candidate cleaning events (delta CIT > {THRESHOLD} C): {len(clean_candidates)}')
    print(clean_candidates.to_string())
"""))

# ── NOTEBOOK METADATA ────────────────────────────────────────────────────────
nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11.0"}
    },
    "cells": cells
}

out = Path(__file__).parent / '1_EDA_standard_sheet.ipynb'
with open(out, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f'Notebook written to: {out}')
print(f'Total cells: {len(cells)}')
