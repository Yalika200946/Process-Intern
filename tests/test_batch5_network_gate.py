import pandas as pd

from pipeline.close_batch5_network_gate import network_hard_gate_status


MANDATORY = ["CPHT2_FLOW_CLOSURE", "CPHT2_MIX_CLOSURE", "ALL_BRANCH_PROPAGATION",
             "TERMINAL_CONFIGURATION", "MEASURED_CIT_REPRODUCTION"]


def test_network_gate_requires_every_mandatory_gate_validated():
    gates = pd.DataFrame({"gate":MANDATORY, "status":["VALIDATED"] * len(MANDATORY)})
    result = network_hard_gate_status(gates)
    assert result["network_complete"] and result["network_status"] == "VALIDATED"


def test_provisional_pilot_cannot_validate_full_network():
    gates = pd.DataFrame({"gate":MANDATORY, "status":["PROVISIONAL", "PROVISIONAL", "BLOCKED", "BLOCKED", "BLOCKED"]})
    result = network_hard_gate_status(gates)
    assert not result["network_complete"]
    assert "MEASURED_CIT_REPRODUCTION" in result["failed_or_provisional_gates"]


def test_missing_terminal_gate_is_explicit():
    gates = pd.DataFrame({"gate":[name for name in MANDATORY if name != "TERMINAL_CONFIGURATION"],
                          "status":["VALIDATED"] * (len(MANDATORY)-1)})
    assert network_hard_gate_status(gates)["missing_gates"] == ["TERMINAL_CONFIGURATION"]


def test_optional_pilot_row_does_not_override_validated_mandatory_gates():
    gates = pd.DataFrame({
        "gate": MANDATORY + ["BRANCH_1FI015_PROPAGATION"],
        "status": ["VALIDATED"] * len(MANDATORY) + ["PROVISIONAL"],
    })
    assert network_hard_gate_status(gates)["network_complete"]
