"""
Shared CIT feature-matrix builder for the model-benchmark / SHAP notebooks (6a, 6b).

Mirrors the feature engineering in `5_HX_fouling_CIT_ranking.ipynb` (sections 2, 3, 8)
exactly, so the XGBoost/RF/LSTM benchmark (6a) and SHAP explainability (6b) explain the
same feature set that `outputs/hx_Q_cleaning_priority.csv` is built from. Extracted here
instead of re-copied into two more notebooks -- same single-source-of-truth rationale as
`cpht_config.py`.
"""
import os
import numpy as np
import pandas as pd
from pathlib import Path

DATA_FILE    = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data')) / 'Process_information_cleaned.csv'
CRUDE_FILE   = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data')) / 'Crude_property_profiled.csv'
FOULING_FILE = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data')) / 'Feature_calculated.csv'

# Same induction-period length notebook 2 uses to skip the early, not-yet-fouling
# part of each run when regressing fouling rate (its `FOULING_LAG_DAYS` constant) --
# reused here so the initiation/after-initiation split is consistent across notebooks.
INITIATION_DAYS = 15
TARGET_TAG = '1TI116.pv'   # CIT -- Coil Inlet Temperature to furnace F101
CHARGE_TAG = '1fi005.pv'   # total crude charge (m3/hr)
O2_TAG     = '1AI001.pv'   # flue-gas O2 %

CP_CRUDE  = 2.2    # kJ/kg.K (assumed, Equations_Reference doc)
RHO_CRUDE = 850    # kg/m3   (assumed)

LEAK_TARGET_HX = 'E113A'  # cold-side outlet of E113A IS the target (CIT) -- see build_cit_feature_matrix

OUTLIER_WINDOW   = 30    # rolling window (days) for z-score detection
OUTLIER_Z_THRESH = 3.0   # |z| > this -> outlier
TEMP_PHYS_LO     = 30    # degC -- physically impossible below this for crude in train
TEMP_PHYS_HI     = 380   # degC -- physically impossible above this for crude in train

# The one confirmed plant-wide TAM in the dataset (verified: all 15 configured HX's
# `days_on_duty` reset to 0 on this date simultaneously, per `Cold_Out_Deviation_Signal.csv`
# -- i.e. the only time the *entire* preheat train is near-clean at once, not just one HX).
# `2_Feature_calculation.ipynb`'s online-clean/shell-switch events only reset one HX at a
# time, so they can't be used for a whole-train clean baseline the way this TAM can.
TAM_DATE            = pd.Timestamp('2024-06-14')
CLEAN_BASELINE_DAYS  = 30   # matches `3a_fouling_rate_forecast.ipynb`'s BASELINE_WINDOW_DAYS

# With the 2021-2026 dataset there can be MORE than one plant-wide TAM. Notebook 2
# already detects them (flow collapse + simultaneous U-jump) and stamps them into
# Feature_calculated.csv event_type columns — so the list is derived from the data
# rather than hardcoded. TAM_DATE above stays as the verified fallback.
TAM_MIN_HX_SIGNAL = 8   # a "plant-wide" TAM = >= this many HX carry event_type='TAM' that day


def get_tam_dates(fouling_file=FOULING_FILE, min_hx=TAM_MIN_HX_SIGNAL):
    """Plant-wide TAM dates as detected by notebook 2 (from Feature_calculated.csv).

    Returns a sorted list of Timestamps; falls back to [TAM_DATE] when the feature
    CSV is missing or carries no TAM events (e.g. before the pipeline first runs).
    Consecutive-day streaks (a TAM stamped over several restart days) collapse to
    the first day; events closer than 30 days apart are treated as one TAM.
    """
    try:
        feat = pd.read_csv(fouling_file, parse_dates=['Timestamp']).set_index('Timestamp')
        ev_cols = [c for c in feat.columns if c.endswith('_event_type')]
        if not ev_cols:
            return [TAM_DATE]
        # event_type persists for the whole run, so a TAM shows up as a months-long
        # streak — the TAM *date* is the first day the plant-wide streak turns on.
        is_tam = (feat[ev_cols] == 'TAM').sum(axis=1) >= min_hx
        starts = is_tam & ~is_tam.shift(1, fill_value=False)
        out = [pd.Timestamp(d) for d in starts[starts].index.normalize()]
        return out or [TAM_DATE]
    except Exception:
        return [TAM_DATE]

HX_CONFIG = {
    'E101AB':  {'title': 'E101AB - Crude vs 1st Side Run',
        'cold': [('1FI007.pv','Crude Inlet Flow','M3/HR'), ('1TI102.pv','Crude Inlet Temp','DEGC'), ('1TI101.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FI010.pv','1SR Inlet Flow','M3/HR'),  ('1TI194.pv','1SR Inlet Temp','DEGC'),   ('1TI103.pv','1SR Outlet Temp','DEGC')]},
    'E101CD':  {'title': 'E101CD - Crude vs 1st Side Run',
        'cold': [('1FI008.pv','Crude Inlet Flow','M3/HR'), ('1TI102.pv','Crude Inlet Temp','DEGC'), ('1TI104.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FI011.pv','1SR Inlet Flow','M3/HR'),  ('1TI194.pv','1SR Inlet Temp','DEGC'),   ('1TI105.pv','1SR Outlet Temp','DEGC')]},
    'E101EF':  {'title': 'E101EF - Crude vs 1st Side Run',
        'cold': [('1FI009.pv','Crude Inlet Flow','M3/HR'), ('1TI102.pv','Crude Inlet Temp','DEGC'), ('1TI109.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FI012.pv','1SR Inlet Flow','M3/HR'),  ('1TI194.pv','1SR Inlet Temp','DEGC'),   ('1TI110.pv','1SR Outlet Temp','DEGC')]},
    'E102':    {'title': 'E102 - Crude vs Kerosene',
        'cold': [('1fi005.pv','Crude Charge Flow (total, no dedicated meter)','M3/HR'), ('1TI107.pv','Crude Inlet Temp','DEGC'),  ('1TI106.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1TI165.pv','Kero Inlet Temp','DEGC'),   ('1TI108.pv','Kero Outlet Temp','DEGC'), ('1FC055.pv','Kero Outlet Flow','M3/HR')]},
    'E103AB':  {'title': 'E103AB - Crude vs 2nd Side Run (2RS-1)',
        'cold': [('1FI015.pv','Crude Inlet Flow','M3/HR'), ('1TI225.pv','Crude Inlet Temp','DEGC'), ('1TI136.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FI018.pv','2RS-1 Inlet Flow','M3/HR'),('4TI107.pv','2RS Inlet Temp','DEGC'),   ('1TI137.pv','2RS-1 Outlet Temp','DEGC')]},
    'E104':    {'title': 'E104 - Crude vs 2nd Side Run',
        'cold': [('1FI015.pv','Crude Inlet Flow','M3/HR'), ('1TI136.pv','Crude Inlet Temp (from E103)','DEGC'), ('1TI112.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1TI195.pv','2RS Inlet Temp','DEGC'),    ('4TI115.pv','2RS Outlet Temp','DEGC')]},
    'E105AB':  {'title': 'E105AB - Crude vs 3rd Side Run',
        'cold': [('1FI015.pv','Crude Inlet Flow','M3/HR'), ('1TI112.pv','Crude Inlet Temp (from E104)','DEGC'), ('1TI114.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FC035.pv','3RS Flow','M3/HR'),         ('1TI195.pv','3RS Inlet Temp','DEGC'),   ('1TI113.pv','3RS Outlet Temp','DEGC')]},
    'E106AB':  {'title': 'E106AB - Crude vs 2nd Side Run (2RS-2)',
        'cold': [('1FI016.pv','Crude Inlet Flow','M3/HR'), ('1TI225.pv','Crude Inlet Temp','DEGC'), ('1TI128.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FI019.pv','2RS-2 Inlet Flow','M3/HR'),('4TI107.pv','2RS Inlet Temp','DEGC'),   ('1TI129.pv','2RS-2 Outlet Temp','DEGC')]},
    'E107AB':  {'title': 'E107AB - Crude vs Gas Oil',
        'cold': [('1FI016.pv','Crude Inlet Flow','M3/HR'), ('1TI128.pv','Crude Inlet Temp (from E106)','DEGC'), ('1TI130.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1TI135.pv','GO Inlet Temp (from E109)','DEGC'), ('1TI131.pv','GO Outlet Temp','DEGC')]},
    'E108AB':  {'title': 'E108AB - Crude vs Residue',
        'cold': [('1FI016.pv','Crude Inlet Flow','M3/HR'), ('1TI130.pv','Crude Inlet Temp (from E107)','DEGC'), ('1TI132.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('439FI003.pv','Residue Flow','M3/HR'),  ('1TI127.pv','Residue Inlet Temp','DEGC'),('1TI133.pv','Residue Outlet Temp','DEGC')]},
    'E109AB':  {'title': 'E109AB - Crude vs Gas Oil',
        'cold': [('1FI016.pv','Crude Inlet Flow','M3/HR'), ('1TI132.pv','Crude Inlet Temp (from E108)','DEGC'), ('1TI134.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1TI163.pv','GO Inlet Temp','DEGC'),     ('1TI135.pv','GO Outlet Temp','DEGC')]},
    'E110ABC': {'title': 'E110ABC - Crude vs Residue',
        'cold': [('1FI017.pv','Crude Inlet Flow','M3/HR'), ('1TI225.pv','Crude Inlet Temp','DEGC'), ('1TI124.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('439FI003.pv','Residue Flow','M3/HR'),  ('1TI133.pv','Residue Inlet Temp','DEGC'),('1TI122.pv','Residue Outlet Temp','DEGC')]},
    'E111':    {'title': 'E111 - Crude vs 3rd Side Run',
        'cold': [('1FI017.pv','Crude Inlet Flow','M3/HR'), ('1TI124.pv','Crude Inlet Temp (from E110)','DEGC'), ('1TI123.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('1FC035.pv','3RS Flow','M3/HR'),         ('1TI113.pv','3RS Inlet Temp (from E105)','DEGC'), ('1TI125.pv','3RS Outlet Temp','DEGC')]},
    'E112AB':  {'title': 'E112AB - Crude vs Residue',
        'cold': [('1FI017.pv','Crude Inlet Flow','M3/HR'), ('1TI123.pv','Crude Inlet Temp (from E111)','DEGC'), ('1TI126.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('439FI003.pv','Residue Flow','M3/HR'),  ('1TI117.pv','Residue Inlet Temp','DEGC'),('1TI127.pv','Residue Outlet Temp','DEGC')]},
    'E112C':   {'title': 'E112C - Crude vs Residue (spare shell)',
        'cold': [('1FI017.pv','Crude Inlet Flow','M3/HR'), ('1TI123.pv','Crude Inlet Temp (from E111)','DEGC'), ('1TI114.pv','Crude Outlet Temp','DEGC')],
        'hot':  [('439FI003.pv','Residue Flow','M3/HR'),  ('1TI117.pv','Residue Inlet Temp','DEGC'),('1TI117B.pv','Residue Outlet Temp','DEGC')]},
    'E113A':   {'title': 'E113A - Crude vs Residue (last HX before Furnace)',
        'cold': [('1fi005.pv','Crude Charge Flow (total, no dedicated meter)','M3/HR'), ('1TI115.pv','Crude Inlet Temp','DEGC'),  ('1TI116.pv','Crude Outlet Temp (CIT)','DEGC'), ('1PI003.pv','Pressure Inlet Furnace','BARG')],
        'hot':  [('439FI003.pv','Residue Flow','M3/HR'),  ('1TI161.pv','Residue from Distillation','DEGC'), ('1TI117.pv','Residue Outlet Temp','DEGC'), ('1PI055.pv','Residue Inlet Pressure','BARG'), ('1PI056.pv','Residue Outlet Pressure','BARG')]},
}


def classify_side(items):
    flow = t_in = t_out = None
    unclassified = []
    for tag, label, unit in items:
        ll = label.lower()
        if unit == 'M3/HR':
            flow = tag
        elif unit == 'DEGC':
            if 'inlet' in ll:
                t_in = tag
            elif 'outlet' in ll:
                t_out = tag
            else:
                unclassified.append(tag)
    if t_in is None and unclassified:
        t_in = unclassified[0]
    return flow, t_in, t_out


def parse_hx(cfg):
    cold_flow, cold_in, cold_out = classify_side(cfg['cold'])
    hot_flow,  hot_in,  hot_out  = classify_side(cfg['hot'])
    return dict(cold_flow=cold_flow, cold_in=cold_in, cold_out=cold_out,
                hot_flow=hot_flow,   hot_in=hot_in,   hot_out=hot_out)


def correct_crude_outliers(df_raw, hx_config=HX_CONFIG, target_tag=TARGET_TAG):
    """Rolling z-score + physical-bounds outlier correction on crude-side temp tags."""
    crude_temp_tags = set()
    for cfg in hx_config.values():
        for tag, label, unit in cfg['cold']:
            if unit == 'DEGC':
                crude_temp_tags.add(tag)
    crude_temp_tags.add(target_tag)
    crude_temp_tags = sorted(crude_temp_tags)

    df = df_raw.copy()
    for tag in crude_temp_tags:
        if tag not in df.columns:
            continue
        s = df[tag].copy()
        roll_mean = s.rolling(OUTLIER_WINDOW, center=True, min_periods=5).mean()
        roll_std  = s.rolling(OUTLIER_WINDOW, center=True, min_periods=5).std()
        z_score   = (s - roll_mean).abs() / roll_std.replace(0, np.nan)
        phys_mask = (s < TEMP_PHYS_LO) | (s > TEMP_PHYS_HI)
        outlier   = (z_score > OUTLIER_Z_THRESH) | phys_mask
        if outlier.sum() > 0:
            fill_vals = roll_mean.where(roll_mean.notna(), s.mean())
            df.loc[outlier, tag] = fill_vals[outlier]
    return df


def compute_q_features(df, streams, charge_tag=CHARGE_TAG):
    """dT_cold, cold-side duty (Q, kW), and charge-normalised Q_norm per HX."""
    charge = df[charge_tag].replace(0, np.nan)

    dT_cold_df = pd.DataFrame(index=df.index)
    duty_df    = pd.DataFrame(index=df.index)
    Q_norm_df  = pd.DataFrame(index=df.index)

    for hx, s in streams.items():
        if s['cold_in'] and s['cold_out']:
            dT_cold_df[hx] = df[s['cold_out']] - df[s['cold_in']]

        if s['cold_flow'] and s['cold_in'] and s['cold_out']:
            Q = RHO_CRUDE * df[s['cold_flow']] * CP_CRUDE * dT_cold_df[hx] / 3600
            duty_df[hx]   = Q
            Q_norm_df[hx] = Q / charge
        elif s['hot_flow'] and s['hot_in'] and s['hot_out']:
            dT_hot = df[s['hot_in']] - df[s['hot_out']]
            Q = RHO_CRUDE * df[s['hot_flow']] * CP_CRUDE * dT_hot / 3600
            duty_df[hx]   = Q
            Q_norm_df[hx] = Q / charge
        elif s['cold_in'] and s['cold_out']:
            Q_norm_df[hx] = dT_cold_df[hx] / charge * 100

    return dT_cold_df, duty_df, Q_norm_df


def load_fouling_state_features(hx_config=HX_CONFIG, fouling_file=FOULING_FILE,
                                 initiation_days=INITIATION_DAYS):
    """
    Per-HX daily fouling-curve state from notebook 2 (`Feature_calculated.csv`):
    `Rf_run` (fouling resistance accumulated since the last clean/switch),
    `U_relative` (U / U_clean_run, 1.0 = clean baseline), and `days_on_duty`
    (days since that HX's last clean/switch -- notebook 2's run-age counter,
    the closest available proxy for "days since last clean").

    Rf_run/U_relative are shifted by 1 day before being handed to the caller:
    both are derived from measured outlet temperatures, and for `E113A` that
    outlet temperature *is* CIT (the prediction target), so using today's value
    would leak today's answer into today's features -- same reasoning as
    `CIT_lag1`. Shifting uniformly for every HX keeps the rule simple and
    consistent instead of special-casing E113A.

    `days_on_duty` is a deterministic run-age counter (not derived from CIT),
    so it is safe to use same-day; `initiation_phase` (`days_on_duty <=
    initiation_days`) is derived from it and marks the early induction period
    of the fouling curve where U hasn't measurably dropped yet (see notebook
    2's `FOULING_LAG_DAYS`), separating "clean-ish, quiet" days from the
    "actively fouling" regime for the model.

    Spare/standby shells (e.g. `E112C`) have no `Rf_run`/`U_relative` on days
    they're offline -- forward-filled (fouling state doesn't change while idle,
    it just stops accumulating), and any still-NaN lead-in (never yet brought
    online) filled with clean-baseline defaults (`Rf_run=0`, `U_relative=1`,
    `days_on_duty=0`, `initiation_phase=1`) rather than dropped, since dropping
    rows on ANY of 16 HX's missing data would gut the usable date range.
    """
    fc = pd.read_csv(fouling_file, index_col='Timestamp', parse_dates=True)

    state = pd.DataFrame(index=fc.index)
    for hx in hx_config:
        rf_col, u_col, day_col = f'{hx}_Rf_run', f'{hx}_U_relative', f'{hx}_days_on_duty'
        if rf_col not in fc.columns:
            continue
        state[f'{hx}_Rf_run_lag1']      = fc[rf_col].shift(1)
        state[f'{hx}_U_relative_lag1']  = fc[u_col].shift(1)
        state[f'{hx}_days_on_duty']     = fc[day_col]
        state[f'{hx}_initiation_phase'] = (fc[day_col] <= initiation_days).astype(int)

    state = state.ffill()
    fill_values = {}
    for hx in hx_config:
        if f'{hx}_Rf_run_lag1' not in state.columns:
            continue
        fill_values[f'{hx}_Rf_run_lag1']      = 0.0
        fill_values[f'{hx}_U_relative_lag1']  = 1.0
        fill_values[f'{hx}_days_on_duty']     = 0
        fill_values[f'{hx}_initiation_phase'] = 1
    return state.fillna(fill_values)


def get_clean_baseline_mask(index, tam_date=None, window_days=CLEAN_BASELINE_DAYS):
    """
    Boolean mask, True for rows within `window_days` after a plant-wide TAM --
    the stretches where the *entire* preheat train is simultaneously near-clean,
    i.e. the "Clean-State Baseline" calibration window (Ujevic Andrijic & Rimac,
    Sensors 2025; same technique `3a_fouling_rate_forecast.ipynb` already uses
    per-HX for its Q-deviation signal, applied here to the whole train for CIT).

    `tam_date` may be a single Timestamp (back-compat), a list of Timestamps, or
    None to use every TAM detected in the data (get_tam_dates) — with 2021-2026
    data the mask is the union of all post-TAM windows, giving the baseline
    model more than one calibration event.
    """
    if tam_date is None:
        tam_dates = get_tam_dates()
    elif isinstance(tam_date, (list, tuple)):
        tam_dates = list(tam_date)
    else:
        tam_dates = [tam_date]
    mask = np.zeros(len(index), dtype=bool)
    for td in tam_dates:
        mask |= (index >= td) & (index < td + pd.Timedelta(days=window_days))
    return mask


def get_start_of_run_points(index, values, tam_date=None, window_days=CLEAN_BASELINE_DAYS):
    """
    For each plant-wide TAM, the single highest-CIT day within its post-TAM
    window -- the truest zero-fouling "Start of Run" reference point, as
    opposed to the whole `window_days`-long window (which includes the
    ramp-up days right after restart, before CIT has actually peaked).

    Returns a dict {tam_date: (peak_timestamp, peak_value)}, one entry per
    TAM that has at least one row inside its window.
    """
    if tam_date is None:
        tam_dates = get_tam_dates()
    elif isinstance(tam_date, (list, tuple)):
        tam_dates = list(tam_date)
    else:
        tam_dates = [tam_date]
    values = pd.Series(values, index=index)
    points = {}
    for td in tam_dates:
        window_mask = (index >= td) & (index < td + pd.Timedelta(days=window_days))
        if window_mask.sum() == 0:
            continue
        in_window = values[window_mask]
        peak_ts = in_window.idxmax()
        points[td] = (peak_ts, in_window.loc[peak_ts])
    return points


def build_cit_feature_matrix(data_file=DATA_FILE, hx_config=HX_CONFIG,
                              leak_target_hx=LEAK_TARGET_HX,
                              target_tag=TARGET_TAG, charge_tag=CHARGE_TAG, o2_tag=O2_TAG,
                              crude_file=CRUDE_FILE, fouling_file=FOULING_FILE,
                              cit_lags=(1, 7), cit_roll=(7,),
                              include_cit_lags=True, include_fouling_state=True):
    """
    Full pipeline: load cleaned process data -> correct crude-temp outliers ->
    compute Q/Q_norm/dT_cold per HX -> assemble the leak-free CIT feature matrix.

    E113A's cold-side outlet IS the target (CIT), so its Q_norm/dT_cold/duty_kW
    are excluded; only E113A_cold_in and E113A_dT_hot are used (no leakage).

    v2 fixes (previous version trained R^2 deeply negative -- see notebook 6a
    diagnosis): CIT is a slow, strongly autocorrelated process variable (near
    random-walk) riding on top of a multi-month level drift (crude slate
    changes, seasonal effects) that none of the 64 same-day HX features could
    explain. A tree model trained on absolute-level features from one period
    was effectively fingerprinting the training era rather than learning a
    relationship that holds across regimes -- catastrophic on any held-out
    period whose levels differ (walk-forward CV R^2 as low as -55). Three
    additions fix this:
      1. `CIT_lag*`/`CIT_roll*` -- yesterday's (and last week's) CIT as a
         feature. This is standard practice for autocorrelated process
         variables: persistence captures the dominant "same as yesterday"
         component, so the remaining HX/crude/season features only need to
         explain the *residual* day-to-day movement -- a much more stationary,
         learnable target. (This reframes the model from "predict CIT level
         from scratch" to "predict today's CIT given yesterday's" -- the more
         honest question anyway, since that's what actually drives the SHAP
         ranking of which HX matters to CIT *change*.)
      2. Crude assay (API, SG, viscosity, MCRT, asphaltenes) and month
         sin/cos -- the two real physical drivers of the slow level drift that
         no HX duty/temperature feature captures (crude slate + seasonal
         ambient effects).
      3. Dropped `{hx}_duty_kW` -- collinear with `{hx}_Q_norm` x
         `total_charge` already in the matrix; cutting it reduces
         dimensionality/overfitting risk without losing information.
    Net effect (XGBoost, chronological 80/20 holdout): R^2 -6.1 -> +0.85,
    RMSE 6.9 -> 1.0 degC.

    v3 addition: per-HX fouling-curve state (`Rf_run_lag1`, `U_relative_lag1`,
    `days_on_duty`, `initiation_phase`) from `load_fouling_state_features` --
    lets the model condition on *where each HX is on its own fouling curve*,
    not just today's instantaneous duty/dT, and is what makes the counterfactual
    "predict CIT if HX X were cleaned today" simulation in 6a meaningful (set
    that HX's Rf_run_lag1/U_relative_lag1/days_on_duty/initiation_phase to their
    post-clean values and re-predict).

    `include_cit_lags=False` / `include_fouling_state=False` (used by
    `6d_clean_baseline_delta_cit.ipynb`): drops the CIT persistence lags and/or
    the fouling-state block entirely. Necessary for the "Expected Clean CIT"
    framing -- that model is trained *only* on clean-baseline rows (see
    `get_clean_baseline_mask`) and must predict CIT from operating conditions
    alone; CIT_lag1/CIT_roll7 (yesterday's actual, already-fouled CIT) and the
    fouling-state features (which directly encode how fouled each HX
    currently is) would both let it shortcut straight to the fouled answer
    instead of learning the clean relationship.

    Returns dict: X, y, df (outlier-corrected), streams, Q_norm_df, duty_df,
    dT_cold_df, cit (== y, kept for readability in caller notebooks).
    """
    df_raw = pd.read_csv(data_file, index_col='Timestamp', parse_dates=True)
    df = correct_crude_outliers(df_raw, hx_config, target_tag)

    streams = {hx: parse_hx(cfg) for hx, cfg in hx_config.items()}
    dT_cold_df, duty_df, Q_norm_df = compute_q_features(df, streams, charge_tag)

    feat = pd.DataFrame(index=df.index)
    for hx, s in streams.items():
        leaky = (hx == leak_target_hx)
        if not leaky:
            if hx in Q_norm_df.columns:
                feat[f'{hx}_Q_norm'] = Q_norm_df[hx]
            if hx in dT_cold_df.columns:
                feat[f'{hx}_dT_cold'] = dT_cold_df[hx]
            # duty_kW intentionally omitted: collinear with Q_norm x total_charge
        if s['hot_in'] and s['hot_out']:
            feat[f'{hx}_dT_hot'] = df[s['hot_in']] - df[s['hot_out']]
        if leaky:
            feat[f'{hx}_cold_in'] = df[s['cold_in']]

    feat['total_charge'] = df[charge_tag]
    feat['flue_O2']      = df[o2_tag]
    feat['month_sin']    = np.sin(2 * np.pi * df.index.month / 12)
    feat['month_cos']    = np.cos(2 * np.pi * df.index.month / 12)

    # Crude assay merged as-of each process day. ffill ONLY (carry the last
    # KNOWN assay forward) -- the previous `.ffill().bfill()` back-filled the
    # lead-in rows before the first assay sample with a *future* assay value,
    # i.e. used tomorrow's crude slate to describe today's crude: a (mild)
    # look-ahead leak. Any leading rows with no prior assay are filled with the
    # first available value but flagged in `crude_leadin_filled` so this
    # last-resort fill is explicit, not silent.
    crude = pd.read_csv(crude_file, parse_dates=['Date']).set_index('Date')
    crude = crude.reindex(df.index).ffill()
    leadin = crude.iloc[:, 0].isna()            # rows before first known assay
    crude = crude.bfill()                       # fill only the flagged lead-in
    feat['crude_leadin_filled'] = leadin.astype(int).values
    for col in crude.columns:
        feat[f'crude_{col}'] = crude[col]

    if include_fouling_state:
        fouling_state = load_fouling_state_features(hx_config, fouling_file)
        feat = feat.join(fouling_state.reindex(df.index))

    target = df[target_tag]
    if include_cit_lags:
        for lag in cit_lags:
            feat[f'CIT_lag{lag}'] = target.shift(lag)
        for win in cit_roll:
            feat[f'CIT_roll{win}'] = target.shift(1).rolling(win).mean()

    leak_check = [c for c in feat.columns
                  if f'{leak_target_hx}_Q_norm'  in c or
                     f'{leak_target_hx}_dT_cold' in c or
                     f'{leak_target_hx}_duty_kW' in c]
    same_day_fouling_leak = [c for c in feat.columns
                             if c.endswith('_Rf_run') or c.endswith('_U_relative')]
    assert (target_tag not in feat.columns and not leak_check and not same_day_fouling_leak), \
        f'Target leakage: {leak_check + same_day_fouling_leak}'

    data = feat.copy()
    data['CIT'] = target
    data = data.dropna()

    X = data.drop(columns=['CIT'])
    y = data['CIT']

    return dict(X=X, y=y, df=df, streams=streams,
                Q_norm_df=Q_norm_df, duty_df=duty_df, dT_cold_df=dT_cold_df, cit=y)
