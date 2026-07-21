import json
from pathlib import Path

import pandas as pd
import pytest

from src.schemas import (
    ContractValidationError,
    EXPECTED_STAGE_IDS,
    REQUIRED_LINEAGE_COLUMNS,
    assert_dataframe_schema,
    contracts_by_stage,
    load_contract_registry,
    required_output_columns,
    validate_contract_registry,
    validate_dataframe_schema,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "data_contracts.yaml"


@pytest.fixture(scope="module")
def registry():
    return load_contract_registry(CONTRACT_PATH)


def test_contract_file_is_json_compatible_yaml():
    parsed = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert parsed["contract_version"] == "1.0.0"


def test_all_stages_00_to_16_are_defined_in_order(registry):
    assert tuple(contract["stage_id"] for contract in registry["contracts"]) == EXPECTED_STAGE_IDS


def test_every_contract_has_complete_definition(registry):
    validate_contract_registry(registry)
    for contract in registry["contracts"]:
        assert contract["required_columns"]
        assert contract["primary_key"]
        assert contract["validation_rules"]
        assert contract["output_path"].endswith(".parquet")
        assert contract["schema_version"]
        assert isinstance(contract["downstream_consumers"], list)


def test_common_lineage_columns_are_required_for_every_output(registry):
    for contract in registry["contracts"]:
        assert REQUIRED_LINEAGE_COLUMNS.issubset(
            required_output_columns(contract, registry)
        )


def test_output_paths_are_unique_and_do_not_target_raw_data(registry):
    output_paths = [contract["output_path"] for contract in registry["contracts"]]
    assert len(output_paths) == len(set(output_paths))
    assert all(not path.startswith("data/raw/") for path in output_paths)


def test_e101g_contract_is_explicitly_inferred(registry):
    stage_05 = contracts_by_stage(registry)["05"]
    required = required_output_columns(stage_05, registry)
    assert {
        "measurement_type",
        "inference_method",
        "uncertainty_lower",
        "uncertainty_upper",
        "source_tags",
        "confidence_level",
    }.issubset(required)
    assert any(
        "E101G measurement_type equals INFERRED" in rule
        for rule in stage_05["validation_rules"]
    )


def test_unconfirmed_operating_limits_have_no_values():
    limits = json.loads(
        (ROOT / "config" / "operating_limits.yaml").read_text(encoding="utf-8")
    )["limits"]
    for definition in limits.values():
        if definition["status"] == "REQUIRES_ENGINEERING_CONFIRMATION":
            assert definition["value"] is None


def test_dataframe_validation_reports_missing_columns(registry):
    errors = validate_dataframe_schema(pd.DataFrame({"run_id": ["r1"]}), "00", registry)
    assert errors
    assert any("processing_timestamp" in error for error in errors)


def test_dataframe_validation_enforces_e101g_inference(registry):
    stage_05 = contracts_by_stage(registry)["05"]
    columns = required_output_columns(stage_05, registry)
    row = {column: "value" for column in columns}
    row.update(
        {
            "timestamp_utc": pd.Timestamp("2026-01-01", tz="UTC"),
            "processing_timestamp": pd.Timestamp("2026-01-02", tz="UTC"),
            "source_data_start": pd.Timestamp("2026-01-01", tz="UTC"),
            "source_data_end": pd.Timestamp("2026-01-01", tz="UTC"),
            "pipeline_stage": "05",
            "hx_id": "E101G",
            "measurement_type": "MEASURED",
            "uncertainty_lower": 1.0,
            "uncertainty_upper": 2.0,
            "data_quality_score": 0.8,
            "is_in_service": True,
        }
    )
    errors = validate_dataframe_schema(pd.DataFrame([row]), "05", registry)
    assert "E101G measurement_type must equal INFERRED" in errors


def test_assert_dataframe_schema_raises_on_failure(registry):
    with pytest.raises(ContractValidationError):
        assert_dataframe_schema(pd.DataFrame(), "16", registry)
