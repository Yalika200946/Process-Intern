"""
Export per-HX time-series for the dashboard's "HX รายตัว" (per-HX detail) tab.

Mirrors the plots in 02_feature_engineering.ipynb section 3.2 (Per-HX Detailed
Dashboard) but as JSON the web can chart: one entry per HX with a down-sampled
daily series of U_relative (fouling sawtooth), Q duty, model predicted_Q vs
actual, deviation, cold-side temps, days_on_duty, the run-boundary events, and
the per-run fouling-rate table. No recompute -- reuses the CSVs the pipeline
already produced.

Run: python pipeline/export_hx_timeseries.py
"""
import os, sys, json
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
NB   = REPO / 'notebooks'
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
OUT  = REPO / 'dashboard' / 'data' / 'hx_timeseries.json'
sys.path.append(str(NB))
from cpht_config import HX_CONFIG
from cpht_features import HX_CONFIG as FULL_CFG, parse_hx   # hot-side tags + labels

STEP = 3   # keep every 3rd day -> ~280 pts/HX instead of 836 (JSON stays small)


def _num(v):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), 3)


def main():
    feat = pd.read_csv(DATA / 'Feature_calculated.csv', parse_dates=['Timestamp']).set_index('Timestamp')
    dev  = pd.read_csv(DATA / 'Q_Deviation_Signal.csv', parse_dates=['Timestamp'])
    # raw cleaned process tags -> hot-side temps + flow (not present in the feature CSVs)
    try:
        proc = pd.read_csv(DATA / 'Process_information_cleaned.csv', parse_dates=['Timestamp']).set_index('Timestamp')
    except FileNotFoundError:
        proc = pd.DataFrame()
    try:
        fr = pd.read_csv(DATA / 'Fouling_Rate_By_Run.csv')
    except FileNotFoundError:
        fr = pd.DataFrame()

    def tag_series(tag, index):
        """Down-sampled values for a raw process tag, aligned to `index` (or [] if absent)."""
        if tag and not proc.empty and tag in proc.columns:
            return [_num(v) for v in proc[tag].reindex(index)]
        return []

    out = {}
    for hx in HX_CONFIG:
        ucol, qcol, dcol, ecol = f'{hx}_U_relative', f'{hx}_Q', f'{hx}_days_on_duty', f'{hx}_event_type'
        if ucol not in feat.columns:
            continue
        base = feat[[c for c in [ucol, qcol, dcol, ecol, f'{hx}_run_id'] if c in feat.columns]].copy()
        # prediction vs actual + temps come from the deviation signal (per-HX long table)
        dh = dev[dev.HX == hx].set_index('Timestamp')
        base = base.join(dh[[c for c in ['predicted_Q', 'deviation', 'cold_in', 'cold_out'] if c in dh.columns]])

        ds = base.iloc[::STEP]                                   # down-sample for the chart

        # hot-side temps + flows come from the raw cleaned process tags (transparency
        # for the effectiveness calc, which uses hot_in): cold_flow falls back to the
        # cpht_config tag (E102/E112C/E113A share total charge, no dedicated meter).
        p = parse_hx(FULL_CFG[hx]) if hx in FULL_CFG else {}
        cold_flow_tag = HX_CONFIG.get(hx, {}).get('cold_flow') or p.get('cold_flow')
        series = dict(
            dates=[d.strftime('%Y-%m-%d') for d in ds.index],
            U_relative=[_num(v) for v in ds[ucol]],
            Q=[_num(v) for v in ds[qcol]] if qcol in ds else [],
            predicted_Q=[_num(v) for v in ds['predicted_Q']] if 'predicted_Q' in ds else [],
            deviation=[_num(v) for v in ds['deviation']] if 'deviation' in ds else [],
            cold_in=[_num(v) for v in ds['cold_in']] if 'cold_in' in ds else [],
            cold_out=[_num(v) for v in ds['cold_out']] if 'cold_out' in ds else [],
            days_on_duty=[_num(v) for v in ds[dcol]] if dcol in ds else [],
            hot_in=tag_series(p.get('hot_in'), ds.index),
            hot_out=tag_series(p.get('hot_out'), ds.index),
            cold_flow=tag_series(cold_flow_tag, ds.index),
            hot_flow=tag_series(p.get('hot_flow'), ds.index),
        )

        # run-boundary events (clean/switch/TAM). Snap each event date to the nearest
        # DOWN-SAMPLED series date: the chart's X-axis is categorical, so a Recharts
        # ReferenceLine only draws when x matches a plotted category — an unsnapped
        # date (event falling between sampled days) would silently vanish.
        sampled = ds.index
        def snap(ts):
            return sampled[np.abs((sampled - ts).values).argmin()] if len(sampled) else ts
        events = []
        if ecol in base.columns:
            ev = base[base[ecol].isin(['DATA_START', 'SWITCH', 'TAM'])]
            prev, seen = None, set()
            for ts, row in ev.iterrows():
                et = row[ecol]
                if et != prev:
                    d = snap(ts).strftime('%Y-%m-%d')
                    if (d, et) not in seen:          # avoid dup after snapping
                        events.append(dict(date=d, type=et))
                        seen.add((d, et))
                prev = et

        # per-run fouling-rate table (reuse 2b/notebook-2 output)
        runs = []
        if not fr.empty:
            for _, r in fr[fr.HX == hx].iterrows():
                runs.append(dict(run=int(r.get('Run', 0)), duration_days=_num(r.get('Duration_days')),
                                 dUrel_per_month=_num(r.get('dUrel_per_month')), R2=_num(r.get('R2')),
                                 reliable=bool((r.get('R2', 0) >= 0.3) and (r.get('N_regression_pts', 0) >= 10))))

        # human-readable hot-stream name from the cpht_features title ("... vs Residue")
        title = FULL_CFG.get(hx, {}).get('title', '')
        hot_name = title.split(' vs ')[-1].split('(')[0].strip() if ' vs ' in title else '—'
        meta = dict(
            hot_stream=hot_name,
            hot_in_tag=p.get('hot_in'), hot_out_tag=p.get('hot_out'),
            cold_flow_tag=cold_flow_tag, hot_flow_tag=p.get('hot_flow'),
            has_hot=bool(series['hot_in']) and bool(series['hot_out']),
            has_flow=bool(series['cold_flow']),
        )
        out[hx] = dict(series=series, events=events, runs=runs, meta=meta)

    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    n_pts = len(next(iter(out.values()))['series']['dates']) if out else 0
    print(f'Wrote {OUT.name}: {len(out)} HX, ~{n_pts} pts each (every {STEP}d), '
          f'{OUT.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
