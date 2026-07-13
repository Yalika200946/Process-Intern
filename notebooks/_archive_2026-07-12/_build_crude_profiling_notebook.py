"""
Helper script: builds 0_profilling_Crude.ipynb from cell definitions.
Run once: python _build_crude_profiling_notebook.py
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
# Crude Property — Profiling & Cleaning

**Source:** `Curde Property.xlsx` (raw assay properties feeding the crude unit)

Goal: profile the raw crude assay sheet, keep only rows with real lab values
(the sheet is a template that also carries empty future-date placeholder rows),
and export a clean daily-indexed crude-property table that
`1_cleaning_data_process.ipynb` will merge onto the process data timeline.

Pipeline:
1. Load & parse raw sheet
2. Drop placeholder rows (no property values)
3. Profile: coverage, missing %, describe()
4. Distribution plots
5. Crude-grade transitions over time (step plot)
6. Export cleaned crude property table
"""))

cells.append(code_cell("""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

%matplotlib inline
plt.rcParams['figure.dpi'] = 100
plt.rcParams['font.size'] = 10
"""))

cells.append(md_cell("""
---
## 1. Load and Parse Data

The sheet has 2 header rows above the real column headers (row index 2), so we
read with `header=2` and rename columns explicitly.
"""))

cells.append(code_cell("""
FILEPATH = r'C:\\Desktop\\Bangchak Internship 2026\\Data\\Curde Property.xlsx'

raw = pd.read_excel(FILEPATH, sheet_name='Sheet1', header=2)
raw = raw.iloc[:, 1:]  # drop leading empty unnamed column
raw.columns = ['Date', 'API', 'SG_15_6C', 'Visc_50C_cSt', 'Visc_100C_cSt', 'MCRT_pct', 'Asphaltenes_pct']

raw['Date'] = pd.to_datetime(raw['Date'], errors='coerce')
raw = raw.dropna(subset=['Date']).reset_index(drop=True)

print(f'Raw rows (with a date): {len(raw)}')
print(f'Date range: {raw[\"Date\"].min().date()} to {raw[\"Date\"].max().date()}')
raw.head()
"""))

cells.append(md_cell("""
---
## 2. Drop Placeholder Rows (No Property Values)

The sheet pre-fills dates through end of 2026 as a template; only rows that
actually carry lab values are real records.
"""))

cells.append(code_cell("""
PROPERTY_COLS = ['API', 'SG_15_6C', 'Visc_50C_cSt', 'Visc_100C_cSt', 'MCRT_pct', 'Asphaltenes_pct']

crude = raw.dropna(subset=PROPERTY_COLS, how='all').copy()
crude = crude.drop_duplicates(subset='Date').sort_values('Date').reset_index(drop=True)

n_placeholder = len(raw) - len(crude)
print(f'Rows with real property values: {len(crude)} / {len(raw)} ({n_placeholder} placeholder rows dropped)')
print(f'Date range with real data: {crude[\"Date\"].min().date()} to {crude[\"Date\"].max().date()}')
"""))

cells.append(md_cell("### 2.1 Daily Coverage Check (gaps within the real-data range)"))

cells.append(code_cell("""
full_range = pd.date_range(crude['Date'].min(), crude['Date'].max(), freq='D')
present = set(crude['Date'])
missing_dates = [d for d in full_range if d not in present]

print(f'Expected daily dates in range: {len(full_range)}')
print(f'Present:                       {len(crude)}')
print(f'Missing within range:          {len(missing_dates)} ({len(missing_dates)/len(full_range)*100:.1f}%)')
if missing_dates:
    print('First missing dates:', [d.date() for d in missing_dates[:10]])
"""))

cells.append(md_cell("""
---
## 3. Profile Properties

### 3.1 Summary Statistics
"""))

cells.append(code_cell("""
crude[PROPERTY_COLS].describe().round(3)
"""))

cells.append(md_cell("### 3.2 Distributions"))

cells.append(code_cell("""
fig, axes = plt.subplots(2, 3, figsize=(15, 8))
axes = axes.ravel()
colors = ['#1f77b4', '#2ca25f', '#e6550d', '#756bb1', '#d62728', '#17becf']

for ax, col, color in zip(axes, PROPERTY_COLS, colors):
    ax.hist(crude[col].dropna(), bins=30, color=color, alpha=0.75, edgecolor='white')
    ax.set_title(col)
    ax.grid(True, alpha=0.3)

fig.suptitle('Crude Property Distributions', fontsize=13, y=1.02)
plt.tight_layout()
plt.show()
"""))

cells.append(md_cell("""
---
## 4. Crude Grade Transitions Over Time

Properties change in step-blocks (crude grade switches), not continuously —
visualize as step plots.
"""))

cells.append(code_cell("""
fig, axes = plt.subplots(len(PROPERTY_COLS), 1, figsize=(16, 3 * len(PROPERTY_COLS)), sharex=True)

for ax, col, color in zip(axes, PROPERTY_COLS, colors):
    ax.step(crude['Date'], crude[col], where='post', color=color, linewidth=1.1)
    ax.set_ylabel(col)
    ax.grid(True, alpha=0.3)

axes[-1].set_xlabel('Date')
fig.suptitle('Crude Property Step-Changes Over Time', fontsize=13, y=1.0)
plt.tight_layout()
plt.show()
"""))

cells.append(md_cell("""
---
## 5. Export Cleaned Crude Property Table

Saved with only the real (non-placeholder) daily records. Gap-filling onto the
full process-data timeline (including forward-fill beyond the last known date)
happens downstream in `1_cleaning_data_process.ipynb`.
"""))

cells.append(code_cell("""
OUTPUT_PATH = r'C:\\Desktop\\Bangchak Internship 2026\\Data\\Crude_property_profiled.csv'

crude_export = crude.set_index('Date')
crude_export.to_csv(OUTPUT_PATH)

print(f'Saved to: {OUTPUT_PATH}')
print(f'Shape: {crude_export.shape}')
print(f'Date range: {crude_export.index.min().date()} to {crude_export.index.max().date()}')
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

out_path = Path(__file__).parent / "0_profilling_Crude.ipynb"
out_path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {out_path}")
