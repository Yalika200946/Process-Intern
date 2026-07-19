"""Regression checks for pipeline selection, artifact lineage, and upload safety."""

from pathlib import Path

import pytest

from backend.server import _safe_filename
from pipeline.run_all import CHAIN, select_chain


ROOT = Path(__file__).resolve().parent.parent


def test_every_production_chain_notebook_exists():
    missing = [name for name in CHAIN if not (ROOT / "notebooks" / name).is_file()]
    assert missing == []


def test_only_selector_requires_one_real_notebook():
    assert select_chain(only="forecast_export") == [
        "production/10_economic_evaluation_forecast_export.ipynb"
    ]
    with pytest.raises(ValueError, match="does not match"):
        select_chain(only="does-not-exist")
    with pytest.raises(ValueError, match="ambiguous"):
        select_chain(only="0")


def test_from_selector_requires_one_real_notebook():
    selected = select_chain(start="fouling_cit_impact_forecast")
    assert selected[0] == "production/04_fouling_cit_impact_forecast.ipynb"
    assert selected == CHAIN[3:]
    with pytest.raises(ValueError, match="does not match"):
        select_chain(start="does-not-exist")


@pytest.mark.parametrize(
    ("untrusted", "expected"),
    [
        ("upload.csv", "upload.csv"),
        ("../../outside.csv", "outside.csv"),
        (r"C:\\temp\\outside.xlsx", "outside.xlsx"),
    ],
)
def test_upload_filename_is_reduced_to_a_basename(untrusted, expected):
    assert _safe_filename(untrusted) == expected


def test_upload_filename_rejects_empty_values():
    for value in ("", " ", ".", ".."):
        with pytest.raises(ValueError):
            _safe_filename(value)


def test_active_forecast_consumers_use_q_deviation_signal():
    """Prevent a stale Cold_Out artifact from silently re-entering production."""
    active_consumers = [
        ROOT / "pipeline" / "phm_analysis.py",
        ROOT / "notebooks" / "production" / "10_economic_evaluation_forecast_export.ipynb",
    ]
    for path in active_consumers:
        text = path.read_text(encoding="utf-8")
        assert "Q_Deviation_Signal.csv" in text, path
        assert "Cold_Out_Deviation_Signal.csv" not in text, path


def test_orchestrator_does_not_execute_source_notebooks_inplace():
    source = (ROOT / "pipeline" / "run_all.py").read_text(encoding="utf-8")
    assert "--inplace" not in source
    assert "executed_notebooks" in source
