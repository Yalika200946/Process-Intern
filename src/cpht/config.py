"""
CPHT tag mapping, HX layout, and file paths for `notebooks_v2/`.

Single source of truth: this module IMPORTS `notebooks/cpht_config.py` and
re-exports its constants, rather than hand-copying them. Two prior bugs in
this project came from exactly the pattern this avoids -- an independently
maintained duplicate of this same config once had wrong E112C tags
(`notebooks/cpht_config.py`'s own header comment), and a separate hand-copied
bypass-capability list once contradicted the real plant data
(`notebooks/bypass_config.py`'s header comment). `notebooks/cpht_config.py`
has no import-time side effects (dict literals + one `os.environ.get()`
call), so importing it directly is safe and is the correct fix here.

`required_tags()`, `V2_OUTPUT_DIR`, and the env-override on `RAW_EXCEL` are
`notebooks_v2`-only additions with no equivalent in the legacy module -- they
don't create a duplication risk because there's nothing in `cpht_config.py`
to drift out of sync with.
"""
import os
import sys
from pathlib import Path

_NOTEBOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "notebooks"
if str(_NOTEBOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_NOTEBOOKS_DIR))

import cpht_config as _legacy  # notebooks/cpht_config.py -- the real source of truth

# --- Re-exported from the legacy module (do not redefine these here) --------
CPHT_1_HX = _legacy.CPHT_1_HX
CPHT_2_HX = _legacy.CPHT_2_HX
HX_CONFIG = _legacy.HX_CONFIG
CHAIN_PREDECESSOR = _legacy.CHAIN_PREDECESSOR
PARALLEL_SHELL_GROUPS = _legacy.PARALLEL_SHELL_GROUPS
CIT_TAG = _legacy.CIT_TAG
TOTAL_CHARGE_TAG = _legacy.TOTAL_CHARGE_TAG

ALL_HX = CPHT_1_HX + CPHT_2_HX

# --- notebooks_v2-only additions (no legacy equivalent) ----------------------

# E101EF <-> E101G spare-shell pair: E101G has zero instrumentation, so its
# flow must be inferred by mass balance when it's in service. (Documented in
# docs/02_Requirement_v2_SSOT.md section 2; not itself a constant in the
# legacy cpht_config.py, so defined here rather than imported.)
E101EF_FLOW_TAGS = ['1FI007.pv', '1FI008.pv', '1FI009.pv']  # E101AB, E101CD, E101EF branches
E101G_INFERENCE_NOTE = (
    "E101G flow = TOTAL_CHARGE_TAG - (1FI007.pv + 1FI008.pv + 1FI009.pv), "
    "valid only when E101EF flow < 10 m3/hr and inferred G flow > 30 m3/hr."
)


def required_tags():
    """Every cold_flow/cold_in/cold_out tag in HX_CONFIG plus network-level tags.

    Used by Notebook 01's ingestion-readiness check and by
    `src/cpht/validation.py`'s schema validator -- single list, not
    duplicated per notebook.
    """
    tags = {CIT_TAG, TOTAL_CHARGE_TAG}
    for cfg in HX_CONFIG.values():
        tags.add(cfg['cold_flow'])
        tags.add(cfg['cold_in'])
        tags.add(cfg['cold_out'])
    return sorted(tags)


# --- Paths ---------------------------------------------------------------
DATA_DIR = os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data')
RAW_EXCEL = DATA_DIR + r'\Process information data (2024-2026).xlsx'

# Where notebooks_v2 write their step outputs -- kept separate from the
# legacy chain's `Data/*.csv` filenames so the two pipelines can run side by
# side without overwriting each other's artifacts during migration.
V2_OUTPUT_DIR = DATA_DIR + r'\v2'
