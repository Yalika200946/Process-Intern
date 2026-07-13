"""
A3: add a prediction-interval cone to dashboard/data/forecast_6mo.json.

The 6c forecast is a single deterministic line (current_dev + rate*t). A point
forecast with no uncertainty over-states confidence. Fouling deviation behaves
like a drifting/random-walk series, so forecast uncertainty grows with the
square-root of the horizon: band(t) = z * sigma_daily * sqrt(t), where
sigma_daily is the std of day-to-day deviation changes in each HX's CURRENT run
(from Cold_Out_Deviation_Signal.csv). z=1.28 -> ~80% interval.

This turns "crosses threshold on day 48" into an honest range the operator can
read as earliest/latest. Run: python add_forecast_intervals.py
"""
import os
import json
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
FC   = REPO / 'dashboard' / 'data' / 'forecast_6mo.json'
Z    = 1.28  # ~80% band

sig = pd.read_csv(DATA / 'Cold_Out_Deviation_Signal.csv', parse_dates=['Timestamp'])
fc = json.loads(FC.read_text(encoding='utf-8'))

def fit_stats(hx):
    """Residual std around the CURRENT run's linear deviation trend + run length.
    Residual (not raw diff) so the trend's own daily step isn't counted as noise
    -- otherwise the cone explodes. Returns (sigma_resid, n_days)."""
    d = sig[sig['HX'] == hx]
    if d.empty or 'run_id' not in d.columns:
        return None, None
    last_run = d['run_id'].dropna().iloc[-1] if d['run_id'].notna().any() else None
    cur = d[d['run_id'] == last_run] if last_run is not None else d.tail(60)
    cur = cur.sort_values('Timestamp')
    dev = cur['deviation'].astype(float).values
    if len(dev) < 8:
        return None, None
    t = np.arange(len(dev), dtype=float)
    b, a = np.polyfit(t, dev, 1)
    resid = dev - (a + b * t)
    return float(np.std(resid)), len(dev)

updated = 0
for hx, e in fc.items():
    s, n = fit_stats(hx)
    proj = e['projected_deviation']
    if s is None or not np.isfinite(s) or s == 0:
        # no reliable fit -> flat 5% band so the chart still shows a cone
        band = [max(0.02 * abs(v), 0.05) * Z for v in proj]
    else:
        # regression-style prediction interval that widens gently with horizon:
        # band(t) = z * sigma_resid * sqrt(1 + t / n_fit)
        band = [Z * s * np.sqrt(1 + i / max(n, 1)) for i in range(len(proj))]
    e['projected_upper'] = [round(v + b, 3) for v, b in zip(proj, band)]
    e['projected_lower'] = [round(max(0.0, v - b), 3) for v, b in zip(proj, band)]
    e['interval_pct'] = 80
    e['sigma_daily'] = round(s, 4) if s else None
    updated += 1

FC.write_text(json.dumps(fc, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Added 80% prediction cones to {updated} HX in {FC.name}')
ex = next(iter(fc))
print(f"  e.g. {ex}: day60 dev={fc[ex]['projected_deviation'][59]} "
      f"[{fc[ex]['projected_lower'][59]}, {fc[ex]['projected_upper'][59]}] sigma={fc[ex]['sigma_daily']}")
