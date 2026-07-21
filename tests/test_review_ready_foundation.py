import json
from pathlib import Path

import pytest

from pipeline.run_all import CHAIN, reaches_terminal
from pipeline.run_integrity import collect_validation_errors
from src.calculations.furnace import calculate_cit_deficit, worst_case_tube_skin
from src.calculations.heat_duty import calculate_cold_side_heat_duty, calculate_q_norm
from src.calculations.mass_balance import infer_e101g_flow
from src.domain.bypass import BYPASS_CONFIG
from src.events.review import append_review, read_reviews
from src.governance import CalculationResult, approval_summary, load_all_registries
from src.optimization.priority import online_recoverable_gain, recommend_action
from src.validation.topology import validate_topology


ROOT = Path(__file__).resolve().parents[1]


def test_governance_registries_validate_with_network_methods_as_candidates():
    registries = load_all_registries()
    summary = approval_summary(registries)
    assert summary["mode"] == "REVIEW"
    assert summary["all_critical_approved"] is False
    assert summary["counts"]["APPROVED"] == 18
    assert summary["counts"]["CANDIDATE"] == 2
    assert summary["counts"]["ASSUMPTION"] == 0
    assert summary["assumption_flags"] == ["METHOD-HYBRID-NETWORK-V1", "METHOD-NETWORK-DIAGNOSTIC-V1"]


def test_calculation_contract_rejects_unknown_vocabulary():
    with pytest.raises(ValueError):
        CalculationResult(1, "kW", "test", "MAGIC")


def test_cold_side_duty_units_and_sign():
    result = calculate_cold_side_heat_duty(100, 850, 2.0, 100, 110)
    assert result.value == pytest.approx(472.2222222)
    assert result.unit == "kW"
    assert result.data_kind == "CALCULATED"
    assert result.approval_status == "APPROVED"


def test_q_norm_requires_positive_charge():
    assert calculate_q_norm(500, 100).value == 5
    with pytest.raises(ValueError):
        calculate_q_norm(500, 0)


def test_e101g_is_inferred_and_negative_residual_is_flagged():
    result = infer_e101g_flow(100, 40, 40, 40)
    assert result.value == 0
    assert result.data_kind == "INFERRED"
    assert result.warnings


def test_cit_deficit_sign_and_worst_tube_skin():
    assert calculate_cit_deficit(250, 258).value == 8
    assert calculate_cit_deficit(260, 258).value == 0
    assert worst_case_tube_skin([380, 401, 390, 399]).value == 401


def test_low_confidence_never_commands_cleaning():
    assert recommend_action(10, "LOW", "full")["action"] == "INVESTIGATE"
    assert recommend_action(10, "HIGH", "none")["action"] == "PLAN_FOR_TAM"
    assert recommend_action(10, "HIGH", "full")["action"] == "CLEAN"


def test_partial_online_gain_uses_duty_fraction():
    assert online_recoverable_gain(4.0, 0.5) == 2.0
    with pytest.raises(ValueError):
        online_recoverable_gain(4.0, 1.1)


def test_current_topology_is_structurally_valid_and_approved_with_traceability():
    assert validate_topology(BYPASS_CONFIG) == []
    gov = json.loads((ROOT / "config" / "engineering_governance.json").read_text(encoding="utf-8"))
    topo = next(row for row in gov["records"] if row["id"] == "TOPO-E112C-E113A")
    assert topo["status"] == "APPROVED"
    assert topo["approver"] == "PROJECT_OWNER_CONFIRMED"
    assert topo["approved_at"] == "2026-07-21"
    assert topo["review_due"] == "2027-07-21"


def test_parallel_topology_conflict_fails_loudly(monkeypatch):
    import src.validation.topology as topology

    broken = dict(topology.HX_CONFIG)
    broken["E112C"] = dict(broken["E112C"], cold_out="wrong-tag")
    monkeypatch.setattr(topology, "HX_CONFIG", broken)
    errors = topology.validate_topology(BYPASS_CONFIG)
    assert any("do not share cold-side tags" in error for error in errors)


def test_partial_chain_does_not_reach_publish_terminal():
    assert reaches_terminal(CHAIN)
    assert reaches_terminal(CHAIN[3:])
    assert not reaches_terminal([CHAIN[0]])


def test_event_reviews_are_append_only(tmp_path):
    audit = tmp_path / "audit.jsonl"
    first = append_review({"event_id": "E113A:2024-01-01", "decision": "CONFIRM"}, audit)
    second = append_review({"event_id": "E113A:2024-01-01", "decision": "REJECT", "note": "operator log mismatch"}, audit)
    records = read_reviews(audit)
    assert [row["review_id"] for row in records] == [first["review_id"], second["review_id"]]
    assert len(audit.read_text(encoding="utf-8").splitlines()) == 2


def test_snapshot_validation_rejects_mixed_generation(tmp_path):
    for name, generation in (("pfd_topology.json", "a"), ("engineering_priority.json", "b")):
        (tmp_path / name).write_text(json.dumps({"_meta": {"generation_id": generation}}), encoding="utf-8")
    errors = collect_validation_errors(tmp_path)
    assert any("Mixed generation IDs" in error for error in errors)
