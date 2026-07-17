# Data Contract Reference

## Purpose

`config/data_contracts.yaml` is the machine-readable interface between canonical pipeline stages 00–16. A stage may read approved upstream outputs, but it must never rely on notebook memory or overwrite an upstream dataset.

The contract file is JSON-compatible YAML. It can therefore be parsed with Python's standard `json` module and does not introduce an undeclared YAML dependency.

## Contract rules

Every stage declares:

- stage ID and name;
- input and output paths;
- required and optional domain columns;
- data types and units;
- primary key and timestamp;
- output time zone and grain;
- null policy and validation rules;
- schema version and downstream consumers.

The following lineage columns are required on every canonical stage output:

| Column | Type | Meaning |
|---|---|---|
| `processing_timestamp` | UTC timestamp | When the output was generated |
| `pipeline_stage` | string | Producing stage ID |
| `schema_version` | string | Dataset schema version |
| `calculation_version` | string | Version of calculations/models used |
| `source_data_start` | UTC timestamp | Earliest source observation represented |
| `source_data_end` | UTC timestamp | Latest source observation represented |
| `data_quality_score` | float, 0–1 | Approved aggregate quality score |
| `measurement_type` | category | `MEASURED`, `CALCULATED`, `INFERRED`, or `ASSUMED` |
| `confidence_level` | category | Confidence classification retained for consumers |

These shared columns are merged with each stage's `required_columns` by `src.schemas.required_output_columns`.

## Stage contract index

| Stage | Purpose | Input | Output | Primary key |
|---|---|---|---|---|
| 00 | Project setup | `config/*.yaml` | `data/interim/00_run_context.parquet` | `run_id` |
| 01 | Business requirements | `config/business_requirements.yaml` | `data/processed/01_business_requirements.parquet` | `requirement_id` |
| 02 | Inventory and tag mapping | `config/tag_mapping.yaml` | `data/processed/02_tag_dictionary.parquet` | `tag_id` |
| 03 | Data ingestion | `data/raw/` | `data/interim/03_process_long.parquet` | `source_file_id`, `source_row_number` |
| 04 | Data quality | Stage 03 process data | `data/processed/04_process_validated.parquet` | `timestamp_utc`, `tag_id` |
| 05 | Alignment and operating modes | Stage 04 validated data | `data/features/05_hx_operating_modes.parquet` | `timestamp_utc`, `hx_id` |
| 06 | Crude properties | Stage 04 plus assay data | `data/gold/06_crude_properties_daily.parquet` | `timestamp_utc` |
| 07 | HX heat duty | Stages 05–06 | `data/gold/07_hx_performance_daily.parquet` | `timestamp_utc`, `hx_id` |
| 08 | Clean baseline | Stage 07 | `data/gold/08_hx_clean_reference.parquet` | timestamp, HX, calculation version |
| 09 | Fouling analysis | Stages 07–08 | `data/gold/09_hx_fouling_daily.parquet` | timestamp, HX, run |
| 10 | Cleaning events | Stage 09 | `data/gold/10_cleaning_events.parquet` | `event_id` |
| 11 | CIT and furnace impact | Stages 09–10 | `data/gold/11_cit_furnace_daily.parquet` | timestamp, constraint |
| 12 | Forecasting | Stages 09 and 11 | `data/gold/12_forecasts.parquet` | origin, horizon, HX, target, model |
| 13 | Cleaning prioritization | Stages 11–12 | `data/gold/13_cleaning_priority.parquet` | decision date, HX |
| 14 | Economic evaluation | Stage 13 and approved assumptions | `data/gold/14_economic_evaluation.parquet` | date, HX, scenario |
| 15 | Dashboard dataset | Approved gold tables | `data/gold/15_dashboard_dataset.parquet` | snapshot, entity, metric |
| 16 | End-to-end validation | All stage outputs and manifests | `data/gold/16_end_to_end_validation.parquet` | run, validation check |

The complete column-level specification is maintained only in `config/data_contracts.yaml` to avoid documentation drift.

## E101G contract

E101G has no direct instrumentation. Any Stage 05 or downstream E101G record must retain:

- `measurement_type = INFERRED`;
- `inference_method`;
- `uncertainty_lower`;
- `uncertainty_upper`;
- `source_tags`;
- `confidence_level`.

The inference formula, tolerance, and confidence classification remain `REQUIRES_ENGINEERING_CONFIRMATION`. Missing inference provenance must fail validation rather than being interpreted as measured data.

## Engineering values

`config/operating_limits.yaml` contains the required F101 constraint names, units where known, and limit directions where confirmed by the approved requirements. Every numerical value is null and every status is `REQUIRES_ENGINEERING_CONFIRMATION`.

No output should calculate limit headroom when its configured limit is null or unapproved.

## Python interface

Use:

```python
from src.schemas import assert_dataframe_schema, load_contract_registry

registry = load_contract_registry()
assert_dataframe_schema(stage_output, stage_id="07", registry=registry)
```

Key functions:

- `load_contract_registry()` parses and validates the registry.
- `contracts_by_stage()` indexes contracts by stage ID.
- `required_output_columns()` merges stage and common lineage requirements.
- `validate_dataframe_schema()` returns validation errors without mutation.
- `assert_dataframe_schema()` fails closed with `ContractValidationError`.
- `contract_summary()` provides a notebook-friendly contract index.

## Test coverage

`tests/test_data_contracts.py` verifies:

- contracts exist in canonical order from 00 through 16;
- every contract contains the formal fields;
- stage columns have declared data types;
- output paths are unique and never target raw data;
- common lineage columns apply to every stage;
- E101G inference provenance is mandatory;
- operating-limit values remain unpopulated;
- dataframe checks fail for missing fields, duplicate keys, and invalid E101G lineage.

Run:

```powershell
python -m pytest tests/test_data_contracts.py -q
```

