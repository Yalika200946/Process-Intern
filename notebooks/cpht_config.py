"""
Shared CPHT (Crude Preheat Train) configuration.

Single source of truth for the 03/04/05/08 notebook series — import from here
instead of redefining HX_CONFIG / group lists per notebook. A stale, independently
maintained copy of this exact config (wrong E112C tags) already caused a bug once
in 01_data_cleaning.ipynb; that's the failure mode this module exists to
prevent going forward.
"""
import os

# CPHT-1: preheats crude ahead of the desalter
CPHT_1_HX = ['E101AB', 'E101CD', 'E101EF', 'E101G', 'E102']

# CPHT-2: raises CIT ahead of the furnace (energy + tube-life impact)
CPHT_2_HX = ['E106AB', 'E110ABC', 'E103AB', 'E107AB', 'E111', 'E104',
             'E108AB', 'E112AB', 'E105AB', 'E112C', 'E109AB', 'E113A']

# Cold-side (crude) tags only — Q duty is computed cold-side-only by design:
# hot-side tags are exactly where the shell-switching/reconfiguration
# complexity lives (E113A/E112C swap, E101EF/E101G swap — see
# 03_operating_state_classification.ipynb), so cold-side keeps Q clean without
# needing to resolve which physical hot-side path was active.
# E101G is excluded — no temperature instrumentation exists for it at all.
HX_CONFIG = {
    'E101AB':  {'cold_flow': '1FI007.pv', 'cold_in': '1TI102.pv', 'cold_out': '1TI101.pv'},
    'E101CD':  {'cold_flow': '1FI008.pv', 'cold_in': '1TI102.pv', 'cold_out': '1TI104.pv'},
    'E101EF':  {'cold_flow': '1FI009.pv', 'cold_in': '1TI102.pv', 'cold_out': '1TI109.pv'},
    'E102':    {'cold_flow': '1fi005.pv', 'cold_in': '1TI107.pv', 'cold_out': '1TI106.pv',
                'flow_source': 'total charge (no dedicated meter)'},
    'E103AB':  {'cold_flow': '1FI015.pv', 'cold_in': '1TI225.pv', 'cold_out': '1TI136.pv'},
    'E104':    {'cold_flow': '1FI015.pv', 'cold_in': '1TI136.pv', 'cold_out': '1TI112.pv',
                'flow_source': 'shared with E103AB (same crude stream)'},
    'E105AB':  {'cold_flow': '1FI015.pv', 'cold_in': '1TI112.pv', 'cold_out': '1TI114.pv',
                'flow_source': 'shared with E103AB (same crude stream)'},
    'E106AB':  {'cold_flow': '1FI016.pv', 'cold_in': '1TI225.pv', 'cold_out': '1TI128.pv'},
    'E107AB':  {'cold_flow': '1FI016.pv', 'cold_in': '1TI128.pv', 'cold_out': '1TI130.pv',
                'flow_source': 'shared with E106AB (same crude stream)'},
    'E108AB':  {'cold_flow': '1FI016.pv', 'cold_in': '1TI130.pv', 'cold_out': '1TI132.pv',
                'flow_source': 'shared with E106AB (same crude stream)'},
    'E109AB':  {'cold_flow': '1FI016.pv', 'cold_in': '1TI132.pv', 'cold_out': '1TI134.pv',
                'flow_source': 'shared with E106AB (same crude stream)'},
    'E110ABC': {'cold_flow': '1FI017.pv', 'cold_in': '1TI225.pv', 'cold_out': '1TI124.pv'},
    'E111':    {'cold_flow': '1FI017.pv', 'cold_in': '1TI124.pv', 'cold_out': '1TI123.pv',
                'flow_source': 'shared with E110ABC (same crude stream)'},
    'E112AB':  {'cold_flow': '1FI017.pv', 'cold_in': '1TI123.pv', 'cold_out': '1TI126.pv',
                'flow_source': 'shared with E110ABC (same crude stream)'},
    'E112C':   {'cold_flow': '1fi005.pv', 'cold_in': '1TI115.pv', 'cold_out': '1TI116.pv',
                'flow_source': 'total charge (no dedicated meter, spare for E113A)'},
    'E113A':   {'cold_flow': '1fi005.pv', 'cold_in': '1TI115.pv', 'cold_out': '1TI116.pv',
                'flow_source': 'total charge (no dedicated meter)'},
}

# cold_out -> cold_in, in flow order — used for both physical-consistency
# outlier checks (01_data_cleaning.ipynb section 4.2) and, here, to
# know each HX's own upstream crude temperature.
CHAIN_PREDECESSOR = {
    '1TI101.pv': '1TI102.pv', '1TI104.pv': '1TI102.pv', '1TI109.pv': '1TI102.pv',
    '1TI106.pv': '1TI107.pv',
    '1TI136.pv': '1TI225.pv', '1TI112.pv': '1TI136.pv', '1TI114.pv': '1TI112.pv',
    '1TI128.pv': '1TI225.pv', '1TI130.pv': '1TI128.pv',
    '1TI132.pv': '1TI130.pv', '1TI134.pv': '1TI132.pv',
    '1TI124.pv': '1TI225.pv', '1TI123.pv': '1TI124.pv', '1TI126.pv': '1TI123.pv',
    '1TI116.pv': '1TI115.pv',
}

# Shells that share the same crude-side cold_in/cold_out (parallel alternates —
# same physical "position" in the train, different physical equipment). Q_kW
# computed from cold_in/cold_out is identical for both; only run/campaign
# segmentation (via Operating_State.csv) tells them apart.
PARALLEL_SHELL_GROUPS = [('E113A', 'E112C')]

CIT_TAG = '1TI116.pv'
TOTAL_CHARGE_TAG = '1fi005.pv'

DATA_DIR = os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data')
PROCESS_WITH_CRUDE_CSV = DATA_DIR + r'\Process_information_with_crude.csv'
OPERATING_STATE_CSV = DATA_DIR + r'\Operating_State.csv'

# --- TAM/shutdown-window detection (01_data_cleaning.ipynb section 4.1) --------------
# Previously hardcoded inline in the notebook cell only -- moved here following this
# module's own established pattern (see header docstring) so these thresholds are
# reviewable/discoverable in one place rather than buried in a large notebook cell.
SHUTDOWN_FLOW_THRESHOLD = 200      # m3/hr; below this, a day is provisionally flagged shutdown
RECOVERY_FLOW_THRESHOLD = 400      # m3/hr; flow must recover above this to end a shutdown window
SHUTDOWN_MARGIN_DAYS = 7           # extra days removed on each side of a detected shutdown
SHUTDOWN_ROLLING_WINDOW_DAYS = 30  # centered rolling median window, for visualization only

# --- Cold-side temperature outlier correction (01_data_cleaning.ipynb section 4.2) ---
# Same rationale as the TAM thresholds above.
CHAIN_TOL_C = 5.0            # deg C tolerance before cold_out < cold_in - tol counts as a chain violation
COLD_TEMP_ROLL_WIN = 30      # days, centered rolling window for z-score outlier detection
COLD_TEMP_Z_THRESH = 3.0     # |z| above this is flagged an outlier
COLD_TEMP_PHYS_MIN = 30      # deg C, physically implausible below this for the crude preheat train
COLD_TEMP_PHYS_MAX = 380     # deg C, physically implausible above this
