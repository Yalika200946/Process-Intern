"""
Export dashboard/data/engineering_priority.json from Data/Engineering_Priority_Score.csv
(notebook 08's risk-based ranking: Probability x Consequence / Effort).

This is the ranking source for the dashboard's Overview & P&ID tab (HX badges, "อันดับ 1"
KPI tile, per-HX detail panel) — a deliberately DIFFERENT lens from the Plan tab's
notebook-16 cost/constraint-aware scheduling optimizer (dashboard/data/cleaning_plan.json).
Keeping them as two separate exports (rather than merging into hx_ranking.json) avoids a
field-name collision: hx_ranking.json already has its own probability_score/consequence_score
computed by a different method (notebook 6b/13).

The CSV has no explicit rank column (only the score) -- added here so the frontend doesn't
need to re-sort/re-rank client-side.

Run: python pipeline/export_engineering_priority.py
"""
import os
from pathlib import Path
import json
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
SRC = DATA / 'Engineering_Priority_Score.csv'
OUT = REPO / 'dashboard' / 'data' / 'engineering_priority.json'


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and not np.isfinite(v):
        return None
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 6)
    return v


def main():
    if not SRC.exists():
        raise SystemExit(f'{SRC} not found — run 08_cleaning_priority_ranking.ipynb first')

    df = pd.read_csv(SRC)
    df = df.sort_values('engineering_priority_score', ascending=False).reset_index(drop=True)
    df['priority_rank'] = df.index + 1

    rows = [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient='records')]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Wrote {OUT.name}: {len(rows)} HX, #1 = '
          f'{rows[0]["HX"]} (score {rows[0]["engineering_priority_score"]})')


if __name__ == '__main__':
    main()
