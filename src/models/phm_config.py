"""
Prognostics & Health Management (PHM) configuration — single source of truth
for the fouling-propagation / RUL / reliability / driver analysis (pipeline/phm_analysis.py).

Edit here to tune the whole PHM layer (same pattern as cpht_config.py).
"""

# risk horizons (days) reported as P(clean needed within N days)
HORIZONS = [30, 60, 90]

# candidate degradation/propagation models compared per HX (C1)
PROP_MODELS = ['linear', 'asymptotic', 'power', 'gp']

# Monte-Carlo RUL (C2)
MC_ITERS = 10000
RANDOM_SEED = 42
# fallback relative SD of fouling rate when a per-HX cross-run estimate is unavailable
# (kept for the rare parametric_normal_fallback path when NO historical rate data exists at
# all, own or topologically pooled -- see src/models/uncertainty.py, ข้อ 8)
RATE_REL_SD_FALLBACK = 0.35
# minimum own historical runs before ข้อ 8's bootstrap uses ONLY this HX's own rate ratios;
# below this it pools with topologically similar HX. Matches WEIBULL_MIN_N's existing "4 runs
# is the low-n cutoff" precedent for consistency across the PHM module.
MIN_N_FOR_OWN_BOOTSTRAP = 4

# ---- multi-source uncertainty composition (ข้อ 9) ----
# ASSUMED (per CLAUDE.md's MEASURED/CALCULATED/INFERRED/ASSUMED discipline) -- no data
# currently characterizes real day-to-day threshold uncertainty; a small +-2% band is an
# engineering placeholder, not a fitted value. REQUIRES_ENGINEERING_CONFIRMATION.
THRESHOLD_UNCERTAINTY_FRAC = 0.02
# ASSUMED fallback for operating-state-driven rate variability. C4's driver model
# (pipeline/phm_analysis.py::run_c4) is currently gated OFF (ข้อ 3 -- leave-HX-out CV doesn't
# beat baseline), so there is NO data-driven operating-state uncertainty estimate available;
# this is a flat multiplicative SD placeholder, not derived from C4. REQUIRES_ENGINEERING_CONFIRMATION.
OPERATING_STATE_UNCERTAINTY_FALLBACK_SD = 0.15

# Weibull survival (C3) — HX with >= this many completed runs get their own scale;
# fewer -> pooled shape with per-HX scale, flagged low-confidence
WEIBULL_MIN_N = 4
SURVIVAL_CURVE_DAYS = 400   # x-range for R(t)/hazard curves

# Driver analysis (C4) — target is per-run fouling rate dRf_per_day (primary metric, changed
# 2026-07-19 to match the mechanistic literature's Rf formulation; see nb_audit.robust_fouling_rate)
DRIVER_TARGET = 'dRf_per_day'
# built from the deviation-signal columns (film-temp proxy, flow) + crude assay
CRUDE_FEATURES = ['API', 'Asphaltenes_pct', 'MCRT_pct', 'Visc_100C_cSt']
# capped at the number of distinct HX (groups) since ข้อ 3's leave-HX-out CV can't have more
# folds than there are HX to hold out -- was "5 arbitrary row-shuffled folds" before 2026-07-20.
DRIVER_CV_FOLDS = 5

# backtest for C1: fit on this leading fraction of each COMPLETED run, predict the
# remaining time-to-clean, compare to the actual run duration (out-of-sample RUL)
# DEPRECATED (2026-07-20, ข้อ 5): superseded by BACKTEST_ORIGIN_FRACTIONS / threshold-crossing
# backtest (src/validation/threshold_backtest.py). No longer referenced by phm_analysis.py;
# kept only in case an external script still imports it. Do not add new consumers.
BACKTEST_FRACTION = 0.6
MIN_RUN_PTS = 12   # skip very short runs when fitting/back-testing

# threshold-crossing backtest (ข้อ 5): forecast origins as fractions of each completed run's
# OBSERVED length -- fit on data visible up to each origin, predict the date of crossing the
# HX's own approved threshold, compare to the actual crossing date.
BACKTEST_ORIGIN_FRACTIONS = (0.30, 0.50, 0.70)

# "near threshold" / imminent-warning horizon (days) -- single source of truth shared by
# export_end_of_run.py's dashboard flag and threshold_backtest.py's false-alarm/missed-warning
# rate (ข้อ 6), so both mean the same thing by "imminent" (was duplicated as a local constant
# in export_end_of_run.py before 2026-07-20; that file now imports it from here).
NEAR_THRESHOLD_DAYS = 60

# 4-state rate-evidence classification (ข้อ 2). Every consumer of a per-HX forecast date
# (export_end_of_run.py, phm_analysis.py C1/C2) must key its display mode off this, not off
# ad-hoc None checks, so "insufficient current evidence" is shown consistently everywhere.
RATE_SOURCE_STATES = ['current_reliable_run', 'previous_reliable_run',
                       'unreliable_current_fit', 'no_forecast']

# ---- event table / censoring taxonomy (ข้อ 11) ----
# run counted as "threshold_driven" if it reached >= this fraction of its trigger-drop
# (1 - U_relative) before the run ended; below this, a real SWITCH clean is "preventive"
# (cleaned before actually needing to).
THRESHOLD_CROSS_TOLERANCE = 0.90
# MUST match export_end_of_run.py's TRIGGER_DROP_FRAC (0.125) -- duplicated here (not
# imported) because pipeline/*.py scripts are run as standalone entry points, not an
# installed package, so there is no existing cross-pipeline-script import path. If
# export_end_of_run.py's TRIGGER_DROP_FRAC ever changes, update this too.
TRIGGER_DROP_FRAC_FOR_EVENT_TABLE = 0.125
EVENT_CATEGORIES = ['threshold_driven_clean', 'preventive_clean', 'TAM', 'shutdown',
                    'mode_transition', 'censored_in_progress']
