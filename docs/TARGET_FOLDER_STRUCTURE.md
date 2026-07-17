# Target Folder Structure

## Principles

- The target structure is additive. Legacy files remain in place until separately approved.
- `notebooks/target/` contains report notebooks only.
- `src/` contains reusable calculations, validation, optimization, and publication code.
- `data/raw` is immutable and normally outside Git.
- Processed tables use Parquet.
- Every output is namespaced by `run_id` until Stage 16 promotes an approved snapshot.
- Detailed repeated plots are saved to `reports/figures/`; notebooks show representative cases and summary plots.

## Proposed structure

```text
furnace-optimization/
├── config/
│   ├── project.yaml
│   ├── paths.yaml
│   ├── schema_versions.yaml
│   ├── source_schemas.yaml
│   ├── tag_mapping.yaml
│   ├── hx_topology.yaml
│   ├── units.yaml
│   ├── engineering_ranges.yaml
│   ├── engineering_limits.yaml
│   ├── data_quality_rules.yaml
│   ├── time_alignment.yaml
│   ├── operating_modes.yaml
│   ├── crude_correlations.yaml
│   ├── crude_defaults.yaml
│   ├── hx_calculations.yaml
│   ├── clean_baseline.yaml
│   ├── fouling.yaml
│   ├── cleaning_events.yaml
│   ├── tam_periods.yaml
│   ├── furnace.yaml
│   ├── forecasting.yaml
│   ├── scenarios.yaml
│   ├── cleaning_constraints.yaml
│   ├── priority_weights.yaml
│   ├── economics.yaml
│   ├── dashboard_datasets.yaml
│   └── release_gates.yaml
│
├── data/
│   ├── raw/                         # immutable source snapshots; gitignored
│   │   └── <source_file_id>/
│   ├── raw_manifest/
│   │   └── source_files.parquet
│   ├── bronze/
│   │   ├── process_long.parquet
│   │   ├── crude_assay_raw.parquet
│   │   └── cleaning_log_raw.parquet
│   ├── silver/
│   │   ├── process_quality_flags.parquet
│   │   ├── process_validated.parquet
│   │   └── process_aligned.parquet
│   ├── reference/
│   │   ├── business_requirements.parquet
│   │   ├── tag_dictionary.parquet
│   │   ├── asset_registry.parquet
│   │   └── hx_topology.parquet
│   ├── gold/
│   │   ├── crude_properties_daily.parquet
│   │   ├── hx_operating_modes.parquet
│   │   ├── hx_runs.parquet
│   │   ├── hx_performance_daily.parquet
│   │   ├── hx_clean_reference.parquet
│   │   ├── hx_fouling_daily.parquet
│   │   ├── hx_fouling_runs.parquet
│   │   ├── cleaning_events.parquet
│   │   ├── cit_furnace_daily.parquet
│   │   ├── forecasts.parquet
│   │   ├── cleaning_priority.parquet
│   │   ├── cleaning_schedule.parquet
│   │   └── economic_evaluation.parquet
│   ├── models/
│   │   ├── registry.parquet
│   │   └── <model_id>/
│   │       ├── artifact.*
│   │       ├── feature_schema.json
│   │       ├── training_manifest.json
│   │       └── validation_metrics.parquet
│   └── published/
│       ├── candidate/<run_id>/
│       └── live/
│           ├── dashboard_manifest.json
│           ├── current_hx_status.json
│           ├── hx_timeseries.json
│           ├── cleaning_events.json
│           ├── forecasts.json
│           ├── cleaning_priority.json
│           ├── cleaning_schedule.json
│           ├── economics.json
│           └── furnace_constraints.json
│
├── notebooks/
│   ├── target/
│   │   ├── 00_project_setup.ipynb
│   │   ├── 01_business_requirements.ipynb
│   │   ├── 02_data_inventory_and_tag_mapping.ipynb
│   │   ├── 03_data_ingestion.ipynb
│   │   ├── 04_data_quality.ipynb
│   │   ├── 05_time_alignment_and_operating_modes.ipynb
│   │   ├── 06_crude_property_calculation.ipynb
│   │   ├── 07_hx_heat_duty_calculation.ipynb
│   │   ├── 08_clean_baseline_model.ipynb
│   │   ├── 09_fouling_analysis.ipynb
│   │   ├── 10_cleaning_event_detection.ipynb
│   │   ├── 11_cit_and_furnace_impact.ipynb
│   │   ├── 12_forecasting.ipynb
│   │   ├── 13_cleaning_prioritization.ipynb
│   │   ├── 14_economic_evaluation.ipynb
│   │   ├── 15_dashboard_dataset.ipynb
│   │   └── 16_end_to_end_validation.ipynb
│   └── legacy/                     # future move only if separately approved
│
├── src/
│   ├── __init__.py
│   ├── config/
│   │   ├── loader.py
│   │   └── schemas.py
│   ├── pipeline/
│   │   ├── run_context.py
│   │   ├── orchestrator.py
│   │   └── manifest.py
│   ├── io/
│   │   ├── process_ingestion.py
│   │   ├── assay_ingestion.py
│   │   ├── source_registry.py
│   │   ├── hashing.py
│   │   └── parquet.py
│   ├── domain/
│   │   ├── tags.py
│   │   ├── topology.py
│   │   ├── operating_modes.py
│   │   ├── run_segmentation.py
│   │   ├── crude_properties.py
│   │   └── clean_reference.py
│   ├── quality/
│   │   ├── rules.py
│   │   ├── shutdown.py
│   │   └── imputation.py
│   ├── time/
│   │   ├── alignment.py
│   │   └── effective_dating.py
│   ├── calculations/
│   │   ├── heat_duty.py
│   │   ├── normalization.py
│   │   ├── fouling.py
│   │   └── furnace.py
│   ├── events/
│   │   ├── cleaning_detection.py
│   │   ├── change_points.py
│   │   └── event_study.py
│   ├── models/
│   │   ├── baselines.py
│   │   ├── clean_baseline.py
│   │   ├── degradation_curves.py
│   │   ├── cit_impact.py
│   │   ├── fouling_forecast.py
│   │   ├── cit_forecast.py
│   │   ├── validation.py
│   │   └── forecast_validation.py
│   ├── optimization/
│   │   ├── priority.py
│   │   ├── scheduler.py
│   │   └── constraints.py
│   ├── economics/
│   │   ├── benefits.py
│   │   ├── costs.py
│   │   └── scenarios.py
│   ├── publish/
│   │   ├── dashboard.py
│   │   ├── schemas.py
│   │   └── serialization.py
│   └── validation/
│       ├── requirements.py
│       ├── tag_mapping.py
│       ├── physical_checks.py
│       ├── hx_physics.py
│       ├── fouling_reliability.py
│       ├── leakage.py
│       ├── approvals.py
│       ├── schemas.py
│       └── end_to_end.py
│
├── tests/
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_ingestion.py
│   │   ├── test_data_quality.py
│   │   ├── test_operating_modes.py
│   │   ├── test_crude_properties.py
│   │   ├── test_heat_duty.py
│   │   ├── test_clean_baseline.py
│   │   ├── test_fouling.py
│   │   ├── test_cleaning_events.py
│   │   ├── test_furnace.py
│   │   ├── test_forecasting.py
│   │   ├── test_priority.py
│   │   ├── test_economics.py
│   │   └── test_publish_schemas.py
│   ├── integration/
│   │   ├── test_stage_contracts.py
│   │   ├── test_small_pipeline.py
│   │   └── test_dashboard_snapshot.py
│   └── fixtures/
│       ├── synthetic_process.parquet
│       ├── synthetic_assay.parquet
│       └── expected/
│
├── reports/
│   ├── figures/
│   │   ├── 02_tag_mapping/
│   │   ├── 03_ingestion/
│   │   ├── 04_data_quality/
│   │   ├── 05_operating_modes/
│   │   ├── 06_crude_properties/
│   │   ├── 07_hx_performance/
│   │   │   └── per_hx/
│   │   ├── 08_clean_baseline/
│   │   │   └── per_hx/
│   │   ├── 09_fouling/
│   │   │   └── per_hx/
│   │   ├── 10_cleaning_events/
│   │   │   └── per_hx/
│   │   ├── 11_furnace_impact/
│   │   ├── 12_forecasting/
│   │   │   └── per_hx/
│   │   ├── 13_prioritization/
│   │   ├── 14_economics/
│   │   ├── 15_dashboard_dataset/
│   │   └── 16_validation/
│   ├── tables/
│   └── validation/
│
├── artifacts/
│   ├── manifests/
│   ├── approvals/
│   ├── validation/
│   └── logs/
│
├── dashboard/
│   └── ... existing application; future version reads data/published/live only
│
└── docs/
    ├── TARGET_PIPELINE.md
    ├── TARGET_PIPELINE_GRAPH.md
    ├── TARGET_FOLDER_STRUCTURE.md
    └── TARGET_NOTEBOOK_CONTENT_PLAN.md
```

## Naming and partitioning rules

- Dataset names describe entities, not notebook numbers.
- Parquet datasets may be partitioned by `year` and, for per-HX tables, `hx_id`.
- Every gold table includes:
  - `pipeline_run_id`
  - `schema_version`
  - `generated_at`
  - `source_data_end`
  - relevant lineage/confidence fields
- Model artifacts are never stored without a training manifest.
- Figure filenames use:

  `stage__figure_name__[hx_id]__[run_id].png`

- Representative plots shown in notebooks should link to the complete per-HX figure directory.

## Legacy coexistence

During migration:

- Existing `notebooks/`, `pipeline/`, `outputs/`, `models/`, and `dashboard/data/` remain untouched.
- Target outputs use new directories and names.
- Comparison adapters may read legacy outputs, but target stages must not overwrite them.
- Removal or relocation of legacy files requires a separate approval after Stage 16 equivalence validation.

