"""Data-contract loading and validation for canonical pipeline stages 00-16.

The contract file is JSON-compatible YAML, allowing validation with the Python
standard library and avoiding an undeclared YAML runtime dependency.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT_PATH = PROJECT_ROOT / "config" / "data_contracts.yaml"
EXPECTED_STAGE_IDS = tuple(f"{stage:02d}" for stage in range(17))
REQUIRED_CONTRACT_FIELDS = {
    "stage_id",
    "stage_name",
    "input_path",
    "required_columns",
    "optional_columns",
    "data_types",
    "units",
    "primary_key",
    "timestamp",
    "time_zone",
    "time_grain",
    "null_policy",
    "validation_rules",
    "output_path",
    "schema_version",
    "downstream_consumers",
}
REQUIRED_LINEAGE_COLUMNS = {
    "processing_timestamp",
    "pipeline_stage",
    "schema_version",
    "calculation_version",
    "source_data_start",
    "source_data_end",
    "data_quality_score",
    "measurement_type",
    "confidence_level",
}
E101G_REQUIRED_COLUMNS = {
    "inference_method",
    "uncertainty_lower",
    "uncertainty_upper",
    "source_tags",
    "confidence_level",
}


class ContractValidationError(ValueError):
    """Raised when a contract definition or dataset violates its schema."""


def load_contract_registry(path: str | Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    """Load the JSON-compatible YAML contract registry."""

    contract_path = Path(path)
    try:
        registry = json.loads(contract_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractValidationError(f"Contract file not found: {contract_path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractValidationError(
            f"Contract file is not valid JSON-compatible YAML: {contract_path}: {exc}"
        ) from exc

    validate_contract_registry(registry)
    return registry


def contracts_by_stage(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Return contracts indexed by two-character stage ID."""

    return {contract["stage_id"]: contract for contract in registry["contracts"]}


def required_output_columns(
    contract: Mapping[str, Any], registry: Mapping[str, Any]
) -> set[str]:
    """Return stage-specific plus common required output columns."""

    return set(contract["required_columns"]) | set(registry["common_output_columns"])


def validate_contract_registry(registry: Mapping[str, Any]) -> None:
    """Validate completeness and internal consistency of all stage contracts."""

    top_level = {"contract_version", "canonical_timezone", "common_output_columns", "contracts"}
    missing_top_level = top_level - set(registry)
    if missing_top_level:
        raise ContractValidationError(
            f"Contract registry missing fields: {sorted(missing_top_level)}"
        )

    common = registry["common_output_columns"]
    missing_lineage = REQUIRED_LINEAGE_COLUMNS - set(common)
    if missing_lineage:
        raise ContractValidationError(
            f"Common output columns missing lineage fields: {sorted(missing_lineage)}"
        )

    contracts = registry["contracts"]
    stage_ids = [contract.get("stage_id") for contract in contracts]
    if tuple(stage_ids) != EXPECTED_STAGE_IDS:
        raise ContractValidationError(
            f"Stages must be ordered 00-16 exactly; found {stage_ids}"
        )

    output_paths: set[str] = set()
    for contract in contracts:
        missing_fields = REQUIRED_CONTRACT_FIELDS - set(contract)
        if missing_fields:
            raise ContractValidationError(
                f"Stage {contract.get('stage_id')} missing fields: {sorted(missing_fields)}"
            )

        required = set(contract["required_columns"])
        optional = set(contract["optional_columns"])
        overlap = required & optional
        if overlap:
            raise ContractValidationError(
                f"Stage {contract['stage_id']} columns both required and optional: "
                f"{sorted(overlap)}"
            )

        declared_stage_columns = required | optional
        missing_types = declared_stage_columns - set(contract["data_types"])
        if missing_types:
            raise ContractValidationError(
                f"Stage {contract['stage_id']} missing data types: {sorted(missing_types)}"
            )

        if not set(contract["primary_key"]).issubset(
            declared_stage_columns | set(common)
        ):
            raise ContractValidationError(
                f"Stage {contract['stage_id']} primary key contains undeclared columns"
            )

        timestamp = contract["timestamp"]
        if timestamp not in declared_stage_columns and timestamp not in common:
            raise ContractValidationError(
                f"Stage {contract['stage_id']} timestamp column is undeclared: {timestamp}"
            )

        output_path = contract["output_path"]
        if output_path in output_paths:
            raise ContractValidationError(f"Duplicate output path: {output_path}")
        output_paths.add(output_path)

        if contract["time_zone"] != registry["canonical_timezone"]:
            raise ContractValidationError(
                f"Stage {contract['stage_id']} output timezone must be "
                f"{registry['canonical_timezone']}"
            )

    stage_05 = contracts_by_stage(registry)["05"]
    stage_05_columns = required_output_columns(stage_05, registry)
    missing_e101g = E101G_REQUIRED_COLUMNS - stage_05_columns
    if missing_e101g:
        raise ContractValidationError(
            f"Stage 05 missing E101G inference fields: {sorted(missing_e101g)}"
        )
    e101g_rules = " ".join(stage_05["validation_rules"])
    if "E101G measurement_type equals INFERRED" not in e101g_rules:
        raise ContractValidationError(
            "Stage 05 must enforce measurement_type = INFERRED for E101G"
        )


def validate_dataframe_schema(
    dataframe: Any,
    stage_id: str,
    registry: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return schema errors for a dataframe-like object without mutating it."""

    active_registry = registry or load_contract_registry()
    contract = contracts_by_stage(active_registry).get(stage_id)
    if contract is None:
        return [f"Unknown stage ID: {stage_id}"]

    columns = set(getattr(dataframe, "columns", ()))
    required = required_output_columns(contract, active_registry)
    errors = [
        f"Missing required column: {column}"
        for column in sorted(required - columns)
    ]

    primary_key = list(contract["primary_key"])
    if not errors and hasattr(dataframe, "duplicated"):
        if bool(dataframe.duplicated(subset=primary_key).any()):
            errors.append(f"Duplicate primary key rows for {primary_key}")

    if "pipeline_stage" in columns:
        invalid_stage = dataframe["pipeline_stage"].dropna().astype(str).ne(stage_id)
        if bool(invalid_stage.any()):
            errors.append(f"pipeline_stage must equal {stage_id}")

    if "measurement_type" in columns:
        # ASSUMED remains accepted for backward compatibility with existing CSVs;
        # new review-mode outputs use the governance vocabulary ASSUMPTION/PREDICTED.
        allowed = {"MEASURED", "CALCULATED", "INFERRED", "PREDICTED", "ASSUMPTION", "ASSUMED"}
        observed = set(dataframe["measurement_type"].dropna().astype(str))
        invalid = observed - allowed
        if invalid:
            errors.append(f"Invalid measurement_type values: {sorted(invalid)}")

    if stage_id == "05" and {"hx_id", "measurement_type"}.issubset(columns):
        e101g = dataframe[dataframe["hx_id"].astype(str).eq("E101G")]
        if not e101g.empty:
            if not e101g["measurement_type"].astype(str).eq("INFERRED").all():
                errors.append("E101G measurement_type must equal INFERRED")
            for column in sorted(E101G_REQUIRED_COLUMNS - {"confidence_level"}):
                if column in e101g and bool(e101g[column].isna().any()):
                    errors.append(f"E101G {column} must not be null")

    return errors


def assert_dataframe_schema(
    dataframe: Any,
    stage_id: str,
    registry: Mapping[str, Any] | None = None,
) -> None:
    """Raise ContractValidationError when dataframe validation fails."""

    errors = validate_dataframe_schema(dataframe, stage_id, registry)
    if errors:
        raise ContractValidationError("; ".join(errors))


def contract_summary(registry: Mapping[str, Any] | None = None) -> Sequence[dict[str, Any]]:
    """Return a compact summary suitable for notebook display."""

    active_registry = registry or load_contract_registry()
    return [
        {
            "stage_id": contract["stage_id"],
            "stage_name": contract["stage_name"],
            "input_path": contract["input_path"],
            "output_path": contract["output_path"],
            "schema_version": contract["schema_version"],
            "downstream_consumers": contract["downstream_consumers"],
        }
        for contract in active_registry["contracts"]
    ]
