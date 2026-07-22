import pytest

from src.reconciliation import reconcile_branch_flow_balance, reconcile_common_value, reconcile_linear_equality


def test_equal_uncertainty_projection_is_hand_calculable():
    result = reconcile_linear_equality([40.0, 30.0, 20.0, 100.0], [1.0] * 4, [1, 1, 1, -1])
    assert result["constraint_residual_before"] == pytest.approx(-10.0)
    assert result["reconciled_values"] == pytest.approx([42.5, 32.5, 22.5, 97.5])
    assert result["constraint_residual_after"] == pytest.approx(0.0, abs=1e-12)


def test_more_uncertain_measurement_receives_larger_adjustment():
    result = reconcile_linear_equality([40.0, 30.0, 20.0, 100.0], [1.0, 1.0, 1.0, 10.0], [1, 1, 1, -1])
    assert abs(result["reconciliation_adjustments"][-1]) > abs(result["reconciliation_adjustments"][0])


def test_branch_flow_contract_preserves_measured_values_and_units():
    result = reconcile_branch_flow_balance(100.0, [40.0, 30.0, 20.0], 1.0, [2.0, 2.0, 2.0])
    assert result["measured_values"] == [40.0, 30.0, 20.0, 100.0]
    assert result["unit"] == "m3/h"
    assert sum(result["reconciled_values"][:3]) == pytest.approx(result["reconciled_values"][3])


def test_common_temperature_reconciliation_keeps_both_sources():
    result = reconcile_common_value(220.0, 224.0, 1.0, 3.0)
    assert result["measured_value"] == 220.0
    assert result["calculated_value"] == 224.0
    assert result["reconciled_value"] == pytest.approx(220.4)


@pytest.mark.parametrize("values,sigmas,code", [([1, 2], [1], "NOT_IDENTIFIABLE"), ([1, 2], [1, 0], "NOT_IDENTIFIABLE")])
def test_invalid_uncertainty_or_shape_is_not_identifiable(values, sigmas, code):
    result = reconcile_linear_equality(values, sigmas, [1, -1])
    assert result["quality"]["warning_code"] == code


def test_negative_reconciled_flow_is_constraint_conflict():
    result = reconcile_linear_equality([10.0, 100.0, 10.0], [10.0, 1.0, 1.0], [1, 1, -1])
    assert result["reconciliation_status"] == "CONSTRAINT_CONFLICT"
    assert not result["quality"]["is_valid"]
