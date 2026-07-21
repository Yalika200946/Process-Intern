from pathlib import Path

import pytest

from src.network.datasheet import _number, read_datasheet_diagnostics
from src.network.hybrid import ALL_HX, CPHT2_BRANCHES, TERMINAL_ALTERNATES, active_terminal


def test_network_has_16_positions_and_17_assets_due_to_terminal_alternate():
    assert len(ALL_HX) == 17
    assert len(set(ALL_HX)) == 17
    assert len(ALL_HX) - (len(TERMINAL_ALTERNATES) - 1) == 16
    assert sum(len(path) for path in CPHT2_BRANCHES.values()) == 10


def test_terminal_selection_respects_operating_state():
    assert active_terminal({"E113A": "NORMAL", "E112C": "OFF"}) == "E113A"
    assert active_terminal({"E113A": "OFF", "E112C": "SUBSTITUTE_ACTIVE"}) == "E112C"


def test_datasheet_number_parser_rejects_ocr_uncertainty():
    assert _number("1,433") == 1433
    assert _number("— (OCR unclear)") is None


def test_real_datasheet_is_partial_and_never_claimed_current():
    path = Path(r"C:\Desktop\Bangchak Internship 2026\Data\Data Sheet Heat Exchanger.xlsx")
    if not path.exists():
        pytest.skip("plant datasheet not available")
    result = read_datasheet_diagnostics(path)
    assert "E101AB" in result
    assert all(row["approval_status"] == "CANDIDATE" for row in result.values())
    assert all("design datasheet" in row["basis"] for row in result.values())
