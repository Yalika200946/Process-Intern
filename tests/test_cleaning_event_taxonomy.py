"""
Regression test for the cleaning-event/bypass status taxonomy added to
`pipeline/export_cleaning_history.py` (`event_status`) and
`src/domain/bypass.py` (`feasibility_label`).

Encodes CLAUDE.md's "do not assume post-TAM periods are perfectly clean"
and "an inferred/candidate event must not silently become confirmed" rules
as an executable check: a TAM-only HX (no bypass/swap capability at all)
must never show a CONFIRMED_CLEAN event outside a known TAM date, because
no maintenance log is wired in yet to actually confirm a mid-run online
clean for it.

Reads whatever is currently on disk (`Data/Cleaning_Events.csv`) rather
than re-running the pipeline -- same convention as
tests/test_dashboard_schema.py. Skips (not fails) when the artifact isn't
present locally.
"""
import os
from pathlib import Path

import pandas as pd
import pytest

from src.domain.bypass import BYPASS_CONFIG, feasibility_label

DATA = Path(os.environ.get("CPHT_DATA_DIR", r"C:\Desktop\Bangchak Internship 2026\Data"))
EVENTS_CSV = DATA / "Cleaning_Events.csv"


def _load_events():
    if not EVENTS_CSV.exists():
        pytest.skip(f"{EVENTS_CSV.name} not present locally (run pipeline/export_cleaning_history.py first)")
    return pd.read_csv(EVENTS_CSV)


def test_confirmed_clean_is_never_emitted_without_a_maintenance_log():
    """No maintenance log is wired into this project yet (see
    docs/UNRESOLVED_ENGINEERING_DECISIONS.md §5.1), so CONFIRMED_CLEAN is
    reserved vocabulary -- every SWITCH event must currently land on
    SWITCH_CANDIDATE or UNEXPLAINED_RECOVERY, never CONFIRMED_CLEAN."""
    df = _load_events()
    assert "event_status" in df.columns
    assert (df["event_status"] != "CONFIRMED_CLEAN").all()


def test_tam_only_hx_never_show_a_confirmed_clean_mid_run():
    """For every HX classified TAM_ONLY (no bypass/swap capability at all --
    src/domain/bypass.feasibility_label), no event_status other than
    CONFIRMED_TAM may appear: a TAM-only HX physically cannot be cleaned
    mid-run, so any SWITCH-derived row for it is, at most, a candidate
    signal (regime change / sensor artifact / crude-assay shift), never a
    confirmed clean."""
    df = _load_events()
    if BYPASS_CONFIG is None or not BYPASS_CONFIG:
        pytest.skip("BYPASS_CONFIG unavailable locally (bypass source Excel missing)")
    tam_only_hx = {hx for hx in df["HX"].unique() if feasibility_label(hx) == "TAM_ONLY"}
    if not tam_only_hx:
        pytest.skip("no TAM_ONLY HX present in this dataset")
    for hx in tam_only_hx:
        sub = df[df["HX"] == hx]
        bad = sub[~sub["event_status"].isin(["CONFIRMED_TAM", "SWITCH_CANDIDATE", "UNEXPLAINED_RECOVERY"])]
        assert bad.empty, f"{hx} (TAM_ONLY) has unexpected event_status values: {bad['event_status'].unique()}"
        assert (sub["event_status"] != "CONFIRMED_CLEAN").all(), f"{hx} (TAM_ONLY) has a CONFIRMED_CLEAN event"
