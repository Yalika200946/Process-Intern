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
