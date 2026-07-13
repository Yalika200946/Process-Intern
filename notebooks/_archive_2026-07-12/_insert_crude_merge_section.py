"""
Inserts a new Section 8 (Crude Property Merge) into 1_cleaning_data_process.ipynb,
between the existing Section 7 (Export Cleaned Data, index 37) and the existing
Section 8 (HX Plots, index 38) — which gets renumbered to Section 9.
Run once: python _insert_crude_merge_section.py
"""
import json
from pathlib import Path

NB_PATH = Path(__file__).parent / "1_cleaning_data_process.ipynb"


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


nb = json.loads(NB_PATH.read_text(encoding="utf-8"))
cells = nb["cells"]

# Sanity check: cell 37 is the export cell, cell 38 is "## 8. Heat Exchanger Plots"
assert "OUTPUT_PATH" in "".join(cells[37]["source"]), "Unexpected cell at index 37"
assert "Heat Exchanger Plots" in "".join(cells[38]["source"]), "Unexpected cell at index 38"

# Renumber existing Section 8 -> Section 9
cells[38]["source"] = [
    line.replace("## 8. Heat Exchanger Plots", "## 9. Heat Exchanger Plots")
    for line in cells[38]["source"]
]

new_cells = []

new_cells.append(md_cell("""
---
## 8. Merge Crude Property Data

Bring in crude assay properties (API, SG, viscosities, MCRT, asphaltenes) from
`Crude_property_profiled.csv` (built in `0_profilling_Crude.ipynb`) onto the
cleaned daily process timeline. Crude property data only has real lab records
from 2023-08-27 to ~2025-06-26, while process data runs through 2026-06-02 —
forward-fill bridges every gap, since crude grade stays constant until the next
recorded change.
"""))

new_cells.append(code_cell("""
CRUDE_PROPERTY_PATH = r'C:\\Desktop\\Bangchak Internship 2026\\Data\\Crude_property_profiled.csv'

crude_prop = pd.read_csv(CRUDE_PROPERTY_PATH, index_col='Date', parse_dates=True)
crude_prop = crude_prop.sort_index()

print(f'Crude property records: {len(crude_prop)}')
print(f'Date range: {crude_prop.index.min().date()} to {crude_prop.index.max().date()}')
crude_prop.head()
"""))

new_cells.append(md_cell("### 8.1 Reindex onto Process Timeline & Forward-fill"))

new_cells.append(code_cell("""
crude_prop_aligned = crude_prop.reindex(data_cleaned.index)

n_before_fill = crude_prop_aligned.isnull().all(axis=1).sum()
crude_prop_aligned = crude_prop_aligned.ffill().bfill()
n_after_fill = crude_prop_aligned.isnull().all(axis=1).sum()

print(f'Process rows: {len(data_cleaned)}')
print(f'Rows with no crude property before fill: {n_before_fill}')
print(f'Rows with no crude property after fill:  {n_after_fill}')

coverage_start = crude_prop.index.min()
coverage_end = crude_prop.index.max()
ffilled_tail = data_cleaned.index[data_cleaned.index > coverage_end]
print(f'\\nReal crude-property coverage: {coverage_start.date()} to {coverage_end.date()}')
if len(ffilled_tail) > 0:
    print(f'Forward-filled (no new lab data) for {len(ffilled_tail)} rows after {coverage_end.date()} '
          f'(up to {ffilled_tail.max().date()}) using the last known crude grade.')
"""))

new_cells.append(md_cell("### 8.2 Sanity Check — Crude Property vs CIT"))

new_cells.append(code_cell("""
fig, axes = plt.subplots(2, 1, figsize=(16, 7), sharex=True)

axes[0].plot(data_cleaned.index, data_cleaned['1TI116.pv'], color='#1f77b4', linewidth=0.9)
axes[0].set_ylabel('DEGC')
axes[0].set_title('CIT — Coil Inlet Temp (1TI116.pv)', fontsize=11, loc='left')
axes[0].grid(True, alpha=0.3)

axes[1].step(crude_prop_aligned.index, crude_prop_aligned['API'], where='post', color='#2ca25f', linewidth=1.0)
axes[1].set_ylabel('API')
axes[1].set_title('Crude API (aligned, forward-filled)', fontsize=11, loc='left')
axes[1].grid(True, alpha=0.3)

if coverage_end < data_cleaned.index.max():
    for ax in axes:
        ax.axvspan(coverage_end, data_cleaned.index.max(), color='gray', alpha=0.12)

axes[-1].set_xlabel('Date')
fig.suptitle('Crude Property Alignment Check (gray = forward-filled beyond last lab record)', fontsize=12, y=1.0)
plt.tight_layout()
plt.show()
"""))

new_cells.append(md_cell("### 8.3 Merge & Export"))

new_cells.append(code_cell("""
data_with_crude = data_cleaned.join(crude_prop_aligned)

OUTPUT_PATH_WITH_CRUDE = r'C:\\Desktop\\Bangchak Internship 2026\\Data\\Process_information_with_crude.csv'
data_with_crude.to_csv(OUTPUT_PATH_WITH_CRUDE)

print(f'Saved to: {OUTPUT_PATH_WITH_CRUDE}')
print(f'Shape: {data_with_crude.shape}  (added {crude_prop_aligned.shape[1]} crude property columns)')
print(f'Remaining NaN in crude columns: {data_with_crude[crude_prop.columns].isnull().sum().sum()}')
"""))

cells[38:38] = new_cells
nb["cells"] = cells

NB_PATH.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Inserted {len(new_cells)} cells. New total: {len(cells)}")
