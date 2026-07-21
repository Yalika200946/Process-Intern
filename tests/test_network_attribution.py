import pytest

from src.network.attribution import build_network_diagnostics, compensation_ratio, equivalent_furnace_duty_mw


def test_equivalent_furnace_duty_units_and_sign():
    assert equivalent_furnace_duty_mw(1.0, 100.0, 850.0, 2.2) == pytest.approx(0.0519444)
    with pytest.raises(ValueError):
        equivalent_furnace_duty_mw(-1.0, 100.0)


def test_compensation_ratio_nominal_and_invalid_denominator():
    assert compensation_ratio(2.0, 0.5) == pytest.approx(0.75)
    assert compensation_ratio(0.0, 0.5) is None


def test_diagnostic_separates_local_condition_from_cit_consequence():
    row = build_network_diagnostics(
        [{"HX": "E1", "clean_q_norm": 10.0, "current_q_norm": 8.0}],
        {"E1": {"cit_gain_C": 2.0, "cit_gain_source": "measured", "cit_gain_n_events": 4}},
        charge_m3_h=500.0,
    )[0]
    assert row["local_q_loss_mw"] == 1.0
    assert row["marginal_cit_recovery_c"] == 2.0
    assert row["confidence"] == "HIGH"
    assert row["approval_status"] == "CANDIDATE"


def test_missing_cit_is_not_silently_zeroed():
    row = build_network_diagnostics(
        [{"HX": "E1", "clean_q_norm": 10.0, "current_q_norm": 8.0}], {}, charge_m3_h=500.0
    )[0]
    assert row["marginal_cit_recovery_c"] is None
    assert "NO_SINGLE_HX_CIT_ESTIMATE" in row["warnings"]
