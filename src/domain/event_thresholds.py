"""
Shared TAM / shell-switch / operating-mask thresholds for the fouling-rate
pipeline (02_hx_performance_operating_modes.ipynb, 04_fouling_cit_impact_forecast.ipynb,
pipeline/compute_fouling_rate.py).

Single source of truth: values below are lifted verbatim from notebook 02
section 3.0 ("Engineering Thresholds"), which is the notebook nb_audit.py's
robust_fouling_rate() and pipeline/compute_fouling_rate.py treat as the
authoritative fouling-run/event definition. Before this module existed,
notebook 04 kept an independently hardcoded TAM_FLOW_THRESH = 200 m3/h (a
copy of src.domain.config.SHUTDOWN_FLOW_THRESHOLD, a threshold meant for
01_data_cleaning.ipynb's much looser "flag any reduced-rate day" shutdown
mask -- a different purpose than notebook 02's "did the whole plant stop for
a TAM" signal) instead of notebook 02's engineering-justified 50 m3/h. That
silent divergence is exactly the failure mode this module exists to prevent
(see src/domain/config.py's own docstring for the same rationale, prior
incident).

Not every notebook-04 threshold belongs here. MIN_CLEAN_INTERVAL_DAYS,
CLEAN_THRESHOLD_PCT, R2_HIGH/R2_MODERATE stay local to notebook 04 -- they
tune notebook 04's own Q-duty-jump event detector (qjump_dates), a noisier
online-only signal than notebook 02's physical U-jump detector, and
deliberately need a wider dedup window (45 days vs. EVENT_DEDUP_DAYS's 7).
"""

# --- Per-HX operating mask (notebook 02 section 3.1) ---------------------------------
# MIN_DT_COLD / MIN_DT_HOT: DCS thermocouple accuracy is about +/-0.5 degC, so
# require a delta-T large enough to confirm real heat transfer, not sensor noise.
MIN_DT_COLD = 3.0     # degC, |T_cold_out - T_cold_in|
MIN_DT_HOT = 2.0       # degC, |T_hot_in - T_hot_out|
# < 10% of that HX's own mean flow = bypass/standby; the flow meter can still
# read positive from meter drift or a bypass leak even while the shell is offline.
MIN_FLOW_FRAC = 0.10   # fraction of mean flow, dynamic per HX
MIN_FLOW_ABS = 15.0    # m3/h absolute floor, backup for low-mean-flow HX
# Physical bounds for S&T HX in crude service: U < 20 is near-zero-LMTD/offline,
# U > 1500 is a pinch artifact.
U_MIN, U_MAX = 20, 1500  # W/m2 degC
MIN_LMTD = 2.0            # degC; below this log(dT1/dT2) is division noise

# --- TAM / shell-switch event detection (notebook 02 section 3.4) --------------------
# TAM_FLOW_THRESH: total charge flow collapsing below this for TAM_MIN_DAYS
# consecutive days = TAM or major upset (plant-level, uses TOTAL_CHARGE_TAG).
TAM_FLOW_THRESH = 50   # m3/h
TAM_MIN_DAYS = 3        # consecutive days
N_HX_TAM_SIGNAL = 4     # >= N of 16 HX jumping U simultaneously = TAM restart, not a lone switch
# SWITCH_JUMP_THRESH: absolute U step (after smoothing) that reads as a clean
# shell going on duty; chosen to filter ~10-20 W/m2 degC day-to-day process noise.
SWITCH_JUMP_THRESH = 40  # W/m2 degC
# SWITCH_JUMP_FRAC: relative version of the same signal, needed because a flat
# 40 W/m2 degC is calibrated for large-duty HX (E103AB/E113A) and is relatively
# too high for small-duty HX (E102/E108AB/E109AB/E110ABC).
SWITCH_JUMP_FRAC = 0.15
SWITCH_SMOOTH_WIN = 3    # days, rolling smooth before diffing (filters single-day spikes)
EVENT_DEDUP_DAYS = 7     # detections within this many days collapse to one event

# --- Post-event clean baseline window (notebook 02 section 3.5 / pipeline) -----------
CLEAN_WINDOW_DAYS = 30   # days after a TAM/switch event used to fit the clean baseline
