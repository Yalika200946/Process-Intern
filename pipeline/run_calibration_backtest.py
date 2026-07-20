"""
Calibration check for the C2 RUL predictive interval (ข้อ 10).

Answers the question Phase 8/9's Monte-Carlo composition can't answer on its own: if the
dashboard says "P90 = 200 days," does the actual outcome fall inside that interval about
90% of the time, historically? A wide-looking interval can still be systematically
miscalibrated (over- or under-confident) -- this is the check that closes the loop.

Method: reuse Phase 5's threshold-crossing backtest origins (30/50/70% into each completed,
non-censored run). At each origin, run the SAME `uncertainty.compose_uncertainty_sources`
Monte Carlo the live dashboard uses, but with data truncated to what was visible at that
origin (no lookahead), and check whether the actual (later-observed) threshold-crossing
day falls inside the resulting P10-P90 / P20-P80 / P25-P75 (i.e. 80/60/50%) intervals, plus
compute PIT values for a calibration histogram.

Deliberately NOT part of run_all.py's fast POST list: running full Monte-Carlo composition
retrospectively at every historical origin is heavier than the regular per-run pipeline
needs, and this is a periodic validation job, not a per-run artifact. Run manually or on a
schedule: python pipeline/run_calibration_backtest.py
"""
import os, sys, json
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
DASH = REPO / 'dashboard' / 'data'
OUT = DASH / 'calibration.json'
sys.path.append(str(REPO))
from src.models import phm_config as C
from src.models import uncertainty as UN
from src.validation import threshold_backtest as TB

MC_ITERS_CALIBRATION = 3000   # smaller than the live C.MC_ITERS -- this runs many more
                              # (HX x run x origin) draws than a single live C2 call does
LEVELS = (50, 80, 90)


def main():
    dev = pd.read_csv(DATA / 'Q_Deviation_Signal.csv', parse_dates=['Timestamp'])
    fr = pd.read_csv(DATA / 'Fouling_Rate_By_Run.csv')
    ttc = pd.read_csv(DATA / 'Time_To_Clean_Prediction.csv').set_index('HX')
    event_table_csv = DATA / 'Event_Table.csv'
    event_table = pd.read_csv(event_table_csv) if event_table_csv.exists() else pd.DataFrame(columns=['HX', 'Run', 'censored'])
    topo_path = DASH / 'pfd_topology.json'
    topo_json = json.loads(topo_path.read_text(encoding='utf-8')) if topo_path.exists() else {}
    et_idx = event_table.set_index(['HX', 'Run'])['censored'] if not event_table.empty else None

    thresholds = {hx: float(ttc.loc[hx, 'threshold']) for hx in ttc.index}
    rng = np.random.default_rng(C.RANDOM_SEED)

    records = []
    for hx in sorted(dev['HX'].dropna().unique()):
        if hx not in thresholds:
            continue
        thr = thresholds[hx]
        d = dev[dev.HX == hx].dropna(subset=['run_id'])
        if d.empty:
            continue
        runs = sorted(d['run_id'].unique())

        for r in runs[:-1]:   # completed runs only
            rr = d[d.run_id == r].sort_values('days_on_duty')
            t = rr['days_on_duty'].to_numpy(float)
            y = rr['deviation'].to_numpy(float)
            if len(t) < C.MIN_RUN_PTS:
                continue
            actual_cross = TB.find_threshold_crossing(t, y, thr, direction='rising')
            if actual_cross is None:
                continue   # right-censored (never crossed within this run) -- not usable for coverage
            censored = et_idx is not None and (hx, int(r)) in et_idx.index and bool(et_idx.loc[(hx, int(r))])
            if censored:
                continue

            rates_by_hx = UN.historical_run_rates(dev, hx, int(r))
            rates_by_hx = {hx: rates_by_hx}
            for h2 in UN.topology_similar_hx(hx, topo_json, k=3):
                rates_by_hx[h2] = UN.historical_run_rates(dev, h2, int(r))

            origins = TB.backtest_origins(t, C.BACKTEST_ORIGIN_FRACTIONS)
            for frac, origin_idx in zip(C.BACKTEST_ORIGIN_FRACTIONS, origins):
                t_origin, y_origin = t[:origin_idx + 1], y[:origin_idx + 1]
                if len(t_origin) < 4:
                    continue
                rate_point, _ = np.polyfit(t_origin, y_origin, 1)
                if not np.isfinite(rate_point) or rate_point <= 0:
                    continue
                cur_dev_point = float(y_origin[-1])
                dev_trunc = dev[(dev.HX == hx) & (dev.run_id == r) & (dev.days_on_duty <= t[origin_idx])]
                samples, sources, _ = UN.compose_uncertainty_sources(
                    rate_point, cur_dev_point, thr, rates_by_hx, hx, topo_json, dev_trunc, r,
                    n_iter=MC_ITERS_CALIBRATION, rng=rng,
                    min_n_for_own_data=C.MIN_N_FOR_OWN_BOOTSTRAP,
                    threshold_uncertainty_frac=C.THRESHOLD_UNCERTAINTY_FRAC,
                    operating_state_fallback_sd=C.OPERATING_STATE_UNCERTAINTY_FALLBACK_SD)
                actual_rul = actual_cross - t[origin_idx]
                if actual_rul < 0:
                    continue   # origin already past the crossing point (shouldn't normally happen)
                records.append(dict(HX=hx, Run=int(r), origin_frac=frac,
                                    actual=float(actual_rul), samples=samples))

    reliability = TB.reliability_diagram_data(records, levels=LEVELS)
    pit = TB.historical_pit_values(records)
    bins = np.linspace(0, 1, 11)
    counts, _ = np.histogram(pit, bins=bins) if pit else (np.zeros(10), bins)

    verdict = 'insufficient_data'
    obs = {r['nominal_pct']: r['observed_pct'] for r in reliability if r['observed_pct'] is not None}
    if obs:
        diffs = [obs[lvl] - lvl for lvl in obs]
        mean_diff = float(np.mean(diffs))
        if abs(mean_diff) <= 7:
            verdict = 'well_calibrated'
        elif mean_diff < 0:
            verdict = 'overconfident'   # observed coverage below nominal -- intervals too narrow
        else:
            verdict = 'underconfident'  # observed coverage above nominal -- intervals too wide

    out = dict(as_of=pd.Timestamp.now().strftime('%Y-%m-%d'),
               n_records=len(records),
               reliability_diagram=reliability,
               pit_histogram=dict(bins=[round(float(b), 2) for b in bins], counts=[int(c) for c in counts]),
               overall_calibration_verdict=verdict,
               note='computed from historical threshold-crossing backtest origins (30/50/70% into each '
                    'completed, non-censored run); run via pipeline/run_calibration_backtest.py, not part '
                    'of the regular fast pipeline chain due to compute cost (ข้อ 10)')
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Wrote {OUT.name}: {len(records)} calibration records, verdict={verdict}, '
          f'reliability={[(r["nominal_pct"], r["observed_pct"]) for r in reliability]}')


if __name__ == '__main__':
    main()
