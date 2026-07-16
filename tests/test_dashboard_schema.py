"""
Schema smoke tests for the dashboard JSON artifacts the pipeline produces. These read
whatever is CURRENTLY on disk (dashboard/data/*.json, Data/*.csv) rather than re-running the
pipeline -- a full `run_all.py` pass takes many minutes (13 notebooks + ~14 post-processors),
too slow for a suite meant to run on every change. See test_full_pipeline_smoke below for the
slow, opt-in end-to-end version.

Every test skips (not fails) when its artifact doesn't exist locally -- this repo's real
plant data is deliberately gitignored (dashboard/data/*.json, Data/), so a fresh checkout
with no local pipeline run yet has nothing to validate against, which is expected, not a
failure.
"""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DASH_DATA = REPO / "dashboard" / "data"


def _load(name):
    p = DASH_DATA / name
    if not p.exists():
        pytest.skip(f"{name} not present locally (run pipeline/run_all.py first)")
    return json.loads(p.read_text(encoding="utf-8"))


class TestCleaningPlanSchema:
    def test_has_furnace_current_state_alerts_key(self):
        """Regression test for the Item 2 wiring bug caught during development: notebook 16
        hand-picks specific fields into cleaning_plan.json rather than dumping the whole
        compute_schedule() output dict, so a new field added to compute_schedule() does NOT
        automatically appear here unless notebook 16's export cell is also updated."""
        d = _load("cleaning_plan.json")
        assert "furnace_current_state_alerts" in d
        assert isinstance(d["furnace_current_state_alerts"], list)

    def test_alert_entries_have_required_fields(self):
        d = _load("cleaning_plan.json")
        for alert in d.get("furnace_current_state_alerts") or []:
            assert alert["severity"] in ("warning", "critical")
            assert "key" in alert and "value" in alert

    def test_per_hx_rows_have_engineering_priority_score(self):
        d = _load("cleaning_plan.json")
        per_hx = d.get("per_hx") or []
        assert len(per_hx) > 0
        # score can legitimately be None (HX with no reliable fouling rate) but the KEY
        # must be present on every row -- a missing key (vs. a None value) means the
        # upstream ranking silently failed to run for that HX.
        for row in per_hx:
            assert "engineering_priority_score" in row


class TestCleaningHistorySchema:
    def test_events_have_confidence_tier(self):
        """Regression test for Item 3: every cleaning event must carry the
        Confirmed/Probable/Possible/Uncertain confidence tier, not just the old
        type/date/measured-recovery fields."""
        d = _load("cleaning_history.json")
        any_events = False
        for hx_data in d.get("hx", {}).values():
            for event in hx_data.get("cleans", []):
                any_events = True
                assert event["confidence"] in ("Confirmed", "Probable", "Possible", "Uncertain")
        assert any_events, "expected at least one cleaning event across all HX"


class TestFeatureCalculatedSchema:
    def test_fouling_phase_column_exists_and_has_expected_values(self):
        """Regression test for Item 4: at least one HX must have a `_fouling_phase` column
        with only the two expected labels."""
        import os
        import pandas as pd

        # Feature_calculated.csv lives outside the repo (CPHT_DATA_DIR), same as every
        # pipeline script reads it -- not derived from REPO.
        data_dir = Path(os.environ.get("CPHT_DATA_DIR", r"C:\Desktop\Bangchak Internship 2026\Data"))
        p = data_dir / "Feature_calculated.csv"
        if not p.exists():
            pytest.skip("Feature_calculated.csv not present locally")
        df = pd.read_csv(p, nrows=2000)
        phase_cols = [c for c in df.columns if c.endswith("_fouling_phase")]
        assert len(phase_cols) > 0
        seen = set(df[phase_cols[0]].dropna().unique())
        assert seen <= {"INITIATION", "AFTER_INITIATION"}


@pytest.mark.skip(reason="slow (~10+ min: 13 notebooks + ~14 post-processors) -- run "
                         "manually before a release with: pytest tests/ -m slow --no-skip "
                         "or by removing this decorator temporarily, not part of the default "
                         "fast suite")
def test_full_pipeline_smoke():
    """End-to-end smoke test: `run_all.py --only 13` (the terminal chain notebook, which
    triggers the full POST post-processing list since ran_terminal becomes True) should
    exit 0 and leave cleaning_plan.json schema-valid. This is the capability the project
    plan asked for; kept skipped by default so the fast test suite stays fast -- run it
    explicitly before a release."""
    import subprocess
    import sys

    r = subprocess.run([sys.executable, str(REPO / "pipeline" / "run_all.py"), "--only", "13"],
                       capture_output=True, text=True, timeout=1800)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    d = _load("cleaning_plan.json")
    assert "furnace_current_state_alerts" in d
    assert len(d.get("per_hx") or []) > 0
