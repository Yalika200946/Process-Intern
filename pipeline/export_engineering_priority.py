"""
Export dashboard/data/engineering_priority.json from Data/Engineering_Priority_Score.csv
(notebook 08's risk-based ranking: Probability x Consequence / Effort).

This is the ranking source for the dashboard's Overview & P&ID tab (HX badges, "อันดับ 1"
KPI tile, per-HX detail panel) — a deliberately DIFFERENT lens from the Plan tab's
notebook-16 cost/constraint-aware scheduling optimizer (dashboard/data/cleaning_plan.json).
Kept as a separate export (rather than merging into hx_ranking.json) so the field names
stay unambiguous.

CORRECTION (Phase 2, 2026-07-17): a previous version of this docstring claimed
hx_ranking.json's probability_score/consequence_score are "computed by a different
method" -- checked against the actual code (11_cit_shap_importance.ipynb cell 17) and
that's wrong: `priority_v2['probability_score'] = eng_priority['probability_score']`
(same for consequence_score, priority_score) -- hx_ranking.json is a direct passthrough
of THIS script's own source file, two hops downstream (08 -> 11 -> 13 -> hx_ranking.json).
It should always carry identical values to engineering_priority.json for a HX that was
part of the same pipeline run. See the consistency check below, added after this
discrepancy was found live during testing (hx_ranking.json served stale numbers because
a partial `run_all.py --only 13` run didn't also re-run notebook 08) -- and
docs/CURRENT_PIPELINE_MAP.md's "Ranking/score traceability" table for the full chain.

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
# hx_ranking.json's ultimate source (via notebook 11 -> notebook 13's passthrough chain,
# see module docstring) -- checked below so a partial rerun that skips notebook 08 can't
# silently leave hx_ranking.json holding a different pipeline run's numbers than this file.
V2_PRIORITY_CSV = REPO / 'outputs' / 'hx_Q_cleaning_priority_v2.csv'
STALENESS_TOLERANCE_S = 120  # generous margin for normal same-run write skew


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


def _check_hx_ranking_consistency():
    """Warn (non-fatal) if hx_ranking.json's ultimate source (V2_PRIORITY_CSV, written by
    notebook 11 from a PAST read of SRC) predates this run's SRC by more than a normal
    same-run write gap -- the exact scenario that produces two different numbers for the
    same HX in engineering_priority.json vs hx_ranking.json, since both are passthroughs
    of the same notebook-08 score but from different pipeline runs."""
    if not V2_PRIORITY_CSV.exists():
        return
    age_diff_s = SRC.stat().st_mtime - V2_PRIORITY_CSV.stat().st_mtime
    if age_diff_s > STALENESS_TOLERANCE_S:
        print(f'WARNING: {SRC.name} is {age_diff_s:.0f}s newer than {V2_PRIORITY_CSV.name} '
              f'({V2_PRIORITY_CSV.relative_to(REPO)}) -- hx_ranking.json (built from the '
              f'latter, via notebook 11 -> 13) will show different engineering_priority_score '
              f'values than this script writes to engineering_priority.json for the same HX. '
              f'This happens when 08_cleaning_priority_ranking.ipynb was re-run without also '
              f're-running 09_cit_model_feature_matrix.ipynb through 13_cit_forecast_export.ipynb '
              f'(e.g. `run_all.py --only 13` or `--from 09` without `--from 08`). Re-run the full '
              f'chain, or notebooks 08 through 13 together, before trusting hx_ranking.json.')


def main():
    if not SRC.exists():
        raise SystemExit(f'{SRC} not found — run 08_cleaning_priority_ranking.ipynb first')

    _check_hx_ranking_consistency()

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
