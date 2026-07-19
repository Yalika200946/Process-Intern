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
RATE_REL_SD_FALLBACK = 0.35

# Weibull survival (C3) — HX with >= this many completed runs get their own scale;
# fewer -> pooled shape with per-HX scale, flagged low-confidence
WEIBULL_MIN_N = 4
SURVIVAL_CURVE_DAYS = 400   # x-range for R(t)/hazard curves

# Driver analysis (C4) — target is per-run fouling rate dRf_per_day (primary metric, changed
# 2026-07-19 to match the mechanistic literature's Rf formulation; see nb_audit.robust_fouling_rate)
DRIVER_TARGET = 'dRf_per_day'
# built from the deviation-signal columns (film-temp proxy, flow) + crude assay
CRUDE_FEATURES = ['API', 'Asphaltenes_pct', 'MCRT_pct', 'Visc_100C_cSt']
DRIVER_CV_FOLDS = 5

# backtest for C1: fit on this leading fraction of each COMPLETED run, predict the
# remaining time-to-clean, compare to the actual run duration (out-of-sample RUL)
BACKTEST_FRACTION = 0.6
MIN_RUN_PTS = 12   # skip very short runs when fitting/back-testing
