"""
Authoritative per-run fouling-rate computation (robust, physically-constrained).

WHY THIS IS A SEPARATE STEP (not in notebook 02): a trustworthy fouling rate needs the
per-HX OPERATING STATE (`Operating_State.csv`) to drop periods when the HX isn't actually
transferring heat (OFF / SUBSTITUTED / BYPASS / mid-clean). That file is produced by
`03_operating_state_classification.ipynb`, which runs AFTER notebook 02 — so the rate is
computed here, right after 03, and OVERWRITES the rough `Fouling_Rate_By_Run.csv` that
notebook 02 wrote as an interactive first pass. All downstream consumers (04, 08, 06/07,
exports) run after this and read the robust file.

Method — `nb_audit.robust_fouling_rate` per HX per run (see METHODOLOGY §3.5):
  in-service mask (NORMAL/SUBSTITUTE_ACTIVE/PARALLEL) · winsorize U_relative to 1.10 ·
  Theil-Sen slope + 95% CI · Rf cross-check (dRf/dt≥0) · recent-60d "current" rate ·
  intra-run recovery split · reliability gate → `reliable` + `rate_flag`.

Physical invariant enforced & asserted: no `reliable` run has slope ≥ 0.

Run: python pipeline/compute_fouling_rate.py
"""
import os, sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
NB   = REPO / 'notebooks'
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
OUT  = DATA / 'Fouling_Rate_By_Run.csv'
sys.path.append(str(NB))
import nb_audit as A
from cpht_config import HX_CONFIG


def main():
    feat = pd.read_csv(DATA / 'Feature_calculated.csv', parse_dates=['Timestamp']).set_index('Timestamp')
    ost_path = DATA / 'Operating_State.csv'
    ost = (pd.read_csv(ost_path, parse_dates=['Timestamp']).set_index('Timestamp')
           if ost_path.exists() else None)
    if ost is None:
        print('WARNING: Operating_State.csv missing — falling back to no state mask '
              '(rates will be less reliable; run 2a first).')

    rows = []
    for hx in HX_CONFIG:
        rid_c, dod_c, ur_c = f'{hx}_run_id', f'{hx}_days_on_duty', f'{hx}_U_relative'
        if rid_c not in feat or ur_c not in feat:
            continue
        rid = feat[rid_c]; dod = feat[dod_c]; ur = feat[ur_c]
        rf = feat.get(f'{hx}_Rf_run'); ucr = feat.get(f'{hx}_U_clean_run')
        evt = feat.get(f'{hx}_event_type')
        state = ost[hx] if (ost is not None and hx in ost.columns) else None

        for run in sorted(rid.dropna().unique()):
            m = (rid == run).values
            res = A.robust_fouling_rate(
                dod[m], ur[m],
                rf_run=(rf[m] if rf is not None else None),
                state=(state[m] if state is not None else None))
            # back-compat metadata columns (kept so existing consumers don't break)
            idx = feat.index[m]
            run_start = idx.min()
            dur = int((dod[m].dropna().max() if dod[m].notna().any() else 0))
            start_evt = None
            if evt is not None and evt[m].notna().any():
                start_evt = str(evt[m].dropna().iloc[0])
            # keep the raw robust slope for transparency, but NULL the primary rate columns
            # for runs that fail the physics/reliability gate — so every downstream consumer
            # that does `dropna(subset=['dUrel_per_month'])` (e.g. 2d) auto-excludes them
            # without any notebook edit, and no unphysical number ever reaches ranking.
            raw = res['dUrel_per_day']
            reliable = bool(res['reliable'])
            primary = raw if reliable else None
            res.update(
                HX=hx, Run=int(run),
                Start_event=start_evt,
                Run_start=str(run_start.date()),
                Duration_days=dur,
                U_clean_run=(round(float(ucr[m].dropna().iloc[0]), 2)
                             if ucr is not None and ucr[m].notna().any() else None),
                dUrel_per_day_raw=raw,
                dUrel_per_day=primary,
                dUrel_per_month=(round(primary * 30, 4) if primary is not None else None),
                p_value=None,  # Theil-Sen: use CI (dUrel_ci_lo/hi) instead of a p-value
            )
            rows.append(res)

    cols = ['HX', 'Run', 'Start_event', 'Run_start', 'Duration_days', 'U_clean_run',
            'dUrel_per_day', 'dUrel_per_month', 'dUrel_per_day_raw', 'dUrel_ci_lo', 'dUrel_ci_hi',
            'dUrel_per_day_recent', 'dRf_per_day', 'R2', 'p_value', 'N_regression_pts',
            'span_days', 'normal_frac', 'n_winsorized', 'split_after_day',
            'reliable', 'rate_flag']
    df = pd.DataFrame(rows).reindex(columns=cols)
    df.to_csv(OUT, index=False)

    rel = df[df['reliable'] == True]  # noqa: E712
    n_bad = int((rel['dUrel_per_day'] >= 0).sum())
    assert n_bad == 0, f'PHYSICAL INVARIANT VIOLATED: {n_bad} reliable run(s) with slope >= 0'
    miss = sorted(set(df['HX']) - set(rel['HX']))
    print(f'Wrote {OUT.name}: {len(df)} runs, {len(rel)} reliable (slope<0, physical), '
          f'{len(df) - len(rel)} flagged')
    print('  flags:', df['rate_flag'].value_counts().to_dict())
    if miss:
        print(f'  HX with no reliable run (rate falls back to partner/None downstream): {miss}')
    print('  physical invariant OK: 0 reliable runs with slope >= 0')


if __name__ == '__main__':
    main()
