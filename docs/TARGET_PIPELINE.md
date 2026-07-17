# Target CPHT and Furnace F101 Analytics Pipeline

## 1. Purpose

This document defines the clean target pipeline for Bangchak Plant 3 CPHT fouling and Furnace F101 decision support. It is an implementation blueprint only. It does not replace, move, or modify the legacy pipeline.

The canonical sequence is:

`00_project_setup → 01_business_requirements → 02_data_inventory_and_tag_mapping → 03_data_ingestion → 04_data_quality → 05_time_alignment_and_operating_modes → 06_crude_property_calculation → 07_hx_heat_duty_calculation → 08_clean_baseline_model → 09_fouling_analysis → 10_cleaning_event_detection → 11_cit_and_furnace_impact → 12_forecasting → 13_cleaning_prioritization → 14_economic_evaluation → 15_dashboard_dataset → 16_end_to_end_validation`

## 2. Target design rules

1. One notebook answers one primary analytical question.
2. Every notebook declares its inputs, outputs, key, grain, configuration, and approval state.
3. Notebooks are reports and orchestration surfaces; reusable calculations live in `src/`.
4. Raw data is immutable. Each ingestion run records source path, checksum, load timestamp, and schema version.
5. Processed analytical tables are Parquet. CSV/JSON is produced only at controlled external interfaces.
6. Every value carries lineage through either column suffixes or metadata:
   - `*_measured`
   - `*_calculated`
   - `*_inferred`
   - `*_assumed`
7. All time-series validation is chronological. Random train-test splitting is prohibited.
8. Future, target, and same-timestamp leakage checks are mandatory model gates.
9. Every model is compared with a simple engineering baseline.
10. Engineering limits and economic assumptions come from versioned configuration files.
11. The dashboard consumes only Stage 15 approved tables.
12. No stage overwrites an upstream table. Corrections create a new dataset version.
13. Every run publishes a manifest containing source hashes, configuration hashes, code revision, row counts, schema versions, and approval status.
14. E101G remains explicitly inferred unless instrumentation changes.
15. Post-TAM observations are candidate reference periods, never automatically labeled perfectly clean.
16. `Q_norm` cannot be labeled as fouling until its formula, units, normalization basis, and expected behavior are approved.

## 3. Canonical keys and grains

| Entity | Primary key | Typical grain |
|---|---|---|
| Raw source file | `source_file_id` | One row per source file |
| Tag dictionary | `tag_id` | One row per canonical tag |
| Process observation | `timestamp_utc`, `tag_id` | Native historian sample |
| Aligned process table | `timestamp`, `asset_id` or wide `timestamp` | Approved analysis interval, normally daily |
| Crude assay | `effective_timestamp`, `crude_grade_id` | Assay/change event |
| HX time series | `timestamp`, `hx_id` | Daily per exchanger |
| HX run/campaign | `hx_id`, `run_id` | One row per service run |
| Cleaning event | `event_id` | One row per inferred/confirmed event |
| Forecast | `forecast_origin`, `horizon_timestamp`, `hx_id`, `target_name` | One row per horizon and target |
| Cleaning priority | `decision_date`, `hx_id` | One row per decision date |
| Dashboard snapshot | `snapshot_id`, entity key | One approved publication |

## 4. Stage contracts

### 00_project_setup

- **Primary analytical question:** Is the project environment, configuration, and run context complete enough to execute reproducibly?
- **Business purpose:** Prevent silent differences between analyst machines, notebook sessions, and dashboard runs.
- **Upstream stage:** None.
- **Input datasets:** Repository metadata; dependency lock files; environment variables; configuration files; legacy-file inventory.
- **Required columns:** For the run manifest: `run_id`, `created_at`, `code_revision`, `python_version`, `dependency_lock_hash`, `config_hash`, `data_root`, `status`.
- **Primary key:** `run_id`.
- **Time grain:** One row per pipeline run.
- **Calculations:** Hashes, environment checks, writable/readable path checks, deterministic seed registration.
- **Engineering checks:** Required engineering configuration files exist; unapproved placeholder limits are identified.
- **Required summary tables:** Environment readiness; configuration approval register.
- **Required diagnostic plots:** None. Setup is tabular.
- **Output datasets:** `artifacts/manifests/run_context.parquet`; machine-readable run manifest JSON.
- **Downstream consumers:** Every stage.
- **Required src modules:** `src/pipeline/run_context.py`, `src/io/hashing.py`, `src/config/loader.py`.
- **Configuration files:** `config/project.yaml`, `config/paths.yaml`, `config/schema_versions.yaml`.
- **Unit tests:** Config loading; deterministic hashing; missing-path failure; run-ID uniqueness.
- **Completion criteria:** A fresh process can create a valid run context without notebook state.
- **Engineering approval required:** Project owner approves environment and configuration ownership, not process calculations.

### 01_business_requirements

- **Primary analytical question:** What decisions must the system support, and what constitutes an acceptable and safe recommendation?
- **Business purpose:** Convert business goals and operating constraints into testable analytical requirements.
- **Upstream stage:** 00.
- **Input datasets:** Approved requirements documents; operator interviews; furnace/HX operating procedures; economic basis.
- **Required columns:** `requirement_id`, `decision_area`, `requirement_text`, `acceptance_test`, `owner`, `approval_status`, `effective_date`.
- **Primary key:** `requirement_id`.
- **Time grain:** Requirement version/effective date.
- **Calculations:** Requirement coverage and traceability only.
- **Engineering checks:** CIT floor, COT, fuel-gas flow/pressure, four pass skin temperatures, stack temperature, O2, draft, online/swap/TAM constraints are represented.
- **Required summary tables:** Requirement traceability matrix; unresolved decision register.
- **Required diagnostic plots:** None.
- **Output datasets:** `data/reference/business_requirements.parquet`; `artifacts/manifests/requirement_traceability.parquet`.
- **Downstream consumers:** Stages 02–16.
- **Required src modules:** `src/validation/requirements.py`.
- **Configuration files:** `config/engineering_limits.yaml`, `config/cleaning_constraints.yaml`, `config/economics.yaml`.
- **Unit tests:** Every mandatory constraint has an owner, unit, approval state, and acceptance test.
- **Completion criteria:** No analytical requirement is represented only in prose or dashboard code.
- **Engineering approval required:** Process engineering, furnace engineering, maintenance, operations, and economics owners.

### 02_data_inventory_and_tag_mapping

- **Primary analytical question:** Which source fields represent each physical measurement, asset, stream, and constraint?
- **Business purpose:** Establish one approved mapping from DCS tags and external files to canonical engineering variables.
- **Upstream stage:** 01.
- **Input datasets:** DCS tag list; `Tags Crude Preheat.xlsx`; HX configuration; PFD/P&ID; bypass list; crude assay schema.
- **Required columns:** `tag_id`, `source_tag`, `canonical_name`, `asset_id`, `stream`, `measurement_type`, `unit_raw`, `unit_canonical`, `lineage_type`, `sensor_available`, `valid_from`, `valid_to`, `approval_status`.
- **Primary key:** `tag_id`; uniqueness constraint on `source_tag` within validity period.
- **Time grain:** Effective-dated mapping.
- **Calculations:** Unit mapping; canonical asset grouping; predecessor/successor topology; sensor-availability flags.
- **Engineering checks:** E112C topology resolved; E101G marked inferred/no direct sensor; shared-flow meters documented; terminal CIT tag confirmed.
- **Required summary tables:** Tag coverage by asset; unresolved/duplicate tag mappings; HX topology table.
- **Required diagnostic plots:** Train topology diagram; tag-coverage heatmap; measurement-lineage map.
- **Output datasets:** `data/reference/tag_dictionary.parquet`; `data/reference/hx_topology.parquet`; `data/reference/asset_registry.parquet`.
- **Downstream consumers:** Stages 03–16.
- **Required src modules:** `src/domain/tags.py`, `src/domain/topology.py`, `src/validation/tag_mapping.py`.
- **Configuration files:** `config/tag_mapping.yaml`, `config/hx_topology.yaml`, `config/units.yaml`.
- **Unit tests:** No duplicate active mappings; all mandatory tags mapped; topology is acyclic; configured tags exist in inventory.
- **Completion criteria:** All approximately 95 tags have an approved disposition: used, optional, unavailable, or excluded.
- **Engineering approval required:** Instrument, process, and operations engineers.

### 03_data_ingestion

- **Primary analytical question:** Can all approved source data be ingested unchanged and traced to its exact source?
- **Business purpose:** Create immutable, reproducible source snapshots.
- **Upstream stage:** 02.
- **Input datasets:** Raw DCS exports; raw crude assay; bypass/configuration workbooks; optional confirmed cleaning log.
- **Required columns:** Process long table: `timestamp_raw`, `source_tag`, `value_raw`, `quality_code`, `source_file_id`; source registry: file path, checksum, size, modified time, schema.
- **Primary key:** `source_file_id`, source row number; uniqueness of `timestamp_raw`, `source_tag`, `source_file_id` where applicable.
- **Time grain:** Native source grain.
- **Calculations:** Parsing, type coercion, source checksums, raw-to-canonical unit conversion in a separate standardized table.
- **Engineering checks:** No value correction or shutdown removal; source units preserved; missing required sheets/tags fail clearly.
- **Required summary tables:** Source-file registry; ingestion row-count reconciliation; parse-error table.
- **Required diagnostic plots:** Source coverage timeline; source-file overlap/gap plot; raw sampling-frequency distribution.
- **Output datasets:** `data/raw_manifest/source_files.parquet`; `data/bronze/process_long.parquet`; `data/bronze/crude_assay_raw.parquet`; `data/bronze/cleaning_log_raw.parquet`.
- **Downstream consumers:** 04 and 06.
- **Required src modules:** `src/io/process_ingestion.py`, `src/io/assay_ingestion.py`, `src/io/source_registry.py`.
- **Configuration files:** `config/source_schemas.yaml`, `config/paths.yaml`, `config/units.yaml`.
- **Unit tests:** Workbook-header parsing; timestamp parsing; duplicate source rows; checksum stability; no source mutation.
- **Completion criteria:** Ingested row counts reconcile to source files and every row has source lineage.
- **Engineering approval required:** Data owner confirms source completeness; no calculation approval.

### 04_data_quality

- **Primary analytical question:** Which measurements are valid, missing, implausible, stale, or unsuitable for each analysis?
- **Business purpose:** Prevent bad sensors and shutdown periods from contaminating engineering conclusions.
- **Upstream stage:** 03.
- **Input datasets:** Bronze process table; tag dictionary; engineering ranges; source quality codes.
- **Required columns:** `timestamp`, `tag_id`, `value_measured`, `quality_flag`, `quality_reason`, `is_shutdown_candidate`, `is_imputed`, `imputation_method`.
- **Primary key:** `timestamp`, `tag_id`.
- **Time grain:** Native and approved resampling grain.
- **Calculations:** Missingness, duplicates, continuity, stuck-sensor detection, physical bounds, robust outliers, cross-tag consistency, shutdown candidates.
- **Engineering checks:** Cold outlet cannot materially undercut inlet; flows/temperatures within approved ranges; no centered-window correction for predictive datasets; imputation is explicit.
- **Required summary tables:** Tag-level DQ scorecard; exclusion/imputation summary; shutdown candidate periods.
- **Required diagnostic plots:** Missingness heatmap; tag coverage timeline; physical-range violation chart; representative raw-vs-cleaned overlays; sampling-gap distribution.
- **Output datasets:** `data/silver/process_quality_flags.parquet`; `data/silver/process_validated.parquet`; `reports/tables/data_quality_summary.parquet`.
- **Downstream consumers:** 05, 06, 07, 11.
- **Required src modules:** `src/quality/rules.py`, `src/quality/shutdown.py`, `src/quality/imputation.py`, `src/validation/physical_checks.py`.
- **Configuration files:** `config/data_quality_rules.yaml`, `config/engineering_ranges.yaml`.
- **Unit tests:** Boundary behavior; no future-looking imputation; quality flags preserved; shutdown rules on synthetic cases.
- **Completion criteria:** Every excluded or modified value has a reason and lineage; critical tags meet approved coverage thresholds.
- **Engineering approval required:** Process/instrument engineers approve ranges and correction rules.

### 05_time_alignment_and_operating_modes

- **Primary analytical question:** At each analysis timestamp, which HX and furnace operating modes were active?
- **Business purpose:** Ensure calculations use only physically comparable, in-service periods.
- **Upstream stage:** 04.
- **Input datasets:** Validated process observations; asset topology; bypass capability; confirmed shutdown/TAM references.
- **Required columns:** `timestamp`, `hx_id`, `operating_mode`, `mode_source`, `mode_confidence`, `is_in_service`, `active_shell_id`, `days_on_duty`, `run_id`.
- **Primary key:** `timestamp`, `hx_id`.
- **Time grain:** Daily target grain, with mode changes retained at finer grain if needed.
- **Calculations:** Time-zone normalization, resampling, as-of alignment, service-run segmentation, E101G inference, E112C/E113A shell selection, mode confidence.
- **Engineering checks:** Mass/flow consistency; only approved in-service modes count toward fouling; mode transitions are reviewable; no backward fill from future modes.
- **Required summary tables:** Mode-duration by HX; run/campaign register; inferred-mode confidence summary.
- **Required diagnostic plots:** Operating-mode timeline; per-HX service availability heatmap; branch-flow inference plot; E112C/E113A representative swap timeline.
- **Output datasets:** `data/silver/process_aligned.parquet`; `data/gold/hx_operating_modes.parquet`; `data/gold/hx_runs.parquet`.
- **Downstream consumers:** 07–14.
- **Required src modules:** `src/time/alignment.py`, `src/domain/operating_modes.py`, `src/domain/run_segmentation.py`.
- **Configuration files:** `config/time_alignment.yaml`, `config/operating_modes.yaml`, `config/cleaning_constraints.yaml`.
- **Unit tests:** Mode boundaries; run-ID stability; E101G inference; shell-swap cases; no future leakage.
- **Completion criteria:** Every HX-day has one mode, source, confidence, and run assignment or an explicit unknown state.
- **Engineering approval required:** Operations/process engineers approve mode logic and inferred equipment behavior.

### 06_crude_property_calculation

- **Primary analytical question:** What crude properties apply to each process timestamp, and how uncertain are calculated properties?
- **Business purpose:** Normalize HX behavior for changing crude quality.
- **Upstream stage:** 03 and 04.
- **Input datasets:** Raw/validated crude assays; aligned process timestamps; approved property correlations.
- **Required columns:** `timestamp`, `crude_grade_id`, `api_measured`, `sg_calculated`, `cp_calculated`, `rho_calculated`, `viscosity_calculated`, `asphaltenes_measured`, `property_source`, `property_confidence`.
- **Primary key:** `timestamp`; assay event key retained.
- **Time grain:** Daily, effective-dated from assay changes.
- **Calculations:** API↔SG conversion; temperature-dependent Cp/density; viscosity/property transformations; controlled forward effective dating.
- **Engineering checks:** Assay validity periods; no use of future assay results before effective date; correlation domain checks; fallback properties clearly marked assumed.
- **Required summary tables:** Assay coverage and grade periods; property-source/assumption register; property ranges by crude grade.
- **Required diagnostic plots:** Crude-grade timeline; key-property trends; property correlation matrix; calculated-vs-reference property checks.
- **Output datasets:** `data/gold/crude_properties_daily.parquet`; `reports/tables/crude_property_summary.parquet`.
- **Downstream consumers:** 07–12 and 14.
- **Required src modules:** `src/domain/crude_properties.py`, `src/time/effective_dating.py`.
- **Configuration files:** `config/crude_correlations.yaml`, `config/crude_defaults.yaml`.
- **Unit tests:** Known API/SG examples; effective-date boundaries; correlation-domain failures; assumed fallback labeling.
- **Completion criteria:** Every modeled timestamp has approved measured/calculated properties or explicit missing/assumed status.
- **Engineering approval required:** Process/laboratory engineers approve correlations and assay timing.

### 07_hx_heat_duty_calculation

- **Primary analytical question:** How much heat duty and apparent conductance does each HX deliver under valid operating conditions?
- **Business purpose:** Establish physically traceable exchanger performance indicators.
- **Upstream stage:** 05 and 06.
- **Input datasets:** Aligned process data; operating modes; crude properties; HX topology/tag mapping.
- **Required columns:** `timestamp`, `hx_id`, `flow_measured`, `t_in_measured`, `t_out_measured`, `delta_t_calculated`, `q_cold_kw_calculated`, `ua_proxy_calculated`, `q_normalized_calculated`, `calculation_valid`, `invalid_reason`.
- **Primary key:** `timestamp`, `hx_id`.
- **Time grain:** Daily per HX.
- **Calculations:** Cold-side mass flow, Cp/rho, heat duty, temperature rise, approved normalization, optional UA/LMTD only where sensor coverage permits.
- **Engineering checks:** Positive heat transfer; valid flow; temperature ordering; shared meters flagged; E101G excluded or inferred; energy-balance cross-check where hot-side data is valid.
- **Required summary tables:** Current and historical HX performance; formula/availability register; invalid-calculation counts.
- **Required diagnostic plots:** Train duty profile; per-HX duty distribution; measured Q vs operating load; energy-balance cross-check; representative HX temperature/duty traces.
- **Output datasets:** `data/gold/hx_performance_daily.parquet`; `data/gold/hx_performance_summary.parquet`.
- **Downstream consumers:** 08–14.
- **Required src modules:** `src/calculations/heat_duty.py`, `src/calculations/normalization.py`, `src/validation/hx_physics.py`.
- **Configuration files:** `config/hx_calculations.yaml`, `config/units.yaml`, `config/hx_topology.yaml`.
- **Unit tests:** Hand-calculated Q examples; unit conversion; shared-flow handling; invalid temperature/flow cases; approved `Q_norm` formula.
- **Completion criteria:** Formula and units are verified, invalid rows are excluded explicitly, and `Q_norm` has engineering approval before fouling use.
- **Engineering approval required:** Heat-transfer/process engineer.

### 08_clean_baseline_model

- **Primary analytical question:** What performance should each HX deliver when acceptably clean at comparable operating conditions?
- **Business purpose:** Separate expected operating-condition effects from degradation.
- **Upstream stage:** 05–07.
- **Input datasets:** HX performance; operating modes/runs; crude properties; candidate clean events/TAM references; manually approved clean windows.
- **Required columns:** `timestamp`, `hx_id`, `baseline_q_predicted`, `baseline_ua_predicted`, `baseline_method`, `clean_reference_id`, `clean_reference_status`, `prediction_lower`, `prediction_upper`.
- **Primary key:** `timestamp`, `hx_id`, `baseline_model_version`.
- **Time grain:** Daily per HX.
- **Calculations:** Candidate clean-window selection; comparable-condition regression; robust reference percentiles; uncertainty; baseline backtesting.
- **Engineering checks:** Post-TAM is only a candidate; clean windows require acceptance criteria; no evaluation point is used in training its own baseline; models beat simple per-HX seasonal/load baselines.
- **Required summary tables:** Clean-reference register; model performance by HX; baseline coverage/uncertainty.
- **Required diagnostic plots:** Candidate clean-window overview; actual vs baseline by representative HX; residuals vs load/crude; chronological validation plot; uncertainty calibration.
- **Output datasets:** `data/gold/hx_clean_reference.parquet`; `data/models/clean_baseline_predictions.parquet`; model registry artifacts with lineage.
- **Downstream consumers:** 09–14.
- **Required src modules:** `src/models/clean_baseline.py`, `src/models/validation.py`, `src/domain/clean_reference.py`.
- **Configuration files:** `config/clean_baseline.yaml`, approved clean-reference table.
- **Unit tests:** No self-training leakage; chronological split; clean-reference status enforcement; baseline comparison.
- **Completion criteria:** Each baseline has traceable training data, uncertainty, baseline comparison, and approval status.
- **Engineering approval required:** Process/HX engineer approves clean references and acceptable residual behavior.

### 09_fouling_analysis

- **Primary analytical question:** How much has each HX degraded, and at what reliable rate?
- **Business purpose:** Quantify fouling severity and deterioration without conflating throughput or operating mode.
- **Upstream stage:** 08.
- **Input datasets:** HX performance; clean-baseline predictions; operating modes and runs; crude properties.
- **Required columns:** `timestamp`, `hx_id`, `run_id`, `performance_ratio_calculated`, `duty_shortfall_kw_calculated`, `rf_proxy_calculated`, `fouling_phase_inferred`, `signal_reliability`; run table includes slopes, confidence intervals, fit model, flags.
- **Primary key:** Daily: `timestamp`, `hx_id`; run summary: `hx_id`, `run_id`.
- **Time grain:** Daily and per service run.
- **Calculations:** Performance ratio, shortfall, Rf proxy, initiation/steady phase, robust Theil–Sen/asymptotic rate, uncertainty and reliability gates.
- **Engineering checks:** In-service mask; no reliable positive fouling reversal; minimum span/points; oscillation/noise gate; Rf sign cross-check; cleaning recovery breaks runs.
- **Required summary tables:** Current fouling status; reliable rates by run; excluded/unreliable-rate register.
- **Required diagnostic plots:** All-HX fouling heatmap; representative reliable run fits; unreliable/noisy examples; rate ranking with intervals; phase-separated degradation plot.
- **Output datasets:** `data/gold/hx_fouling_daily.parquet`; `data/gold/hx_fouling_runs.parquet`; `data/gold/hx_fouling_current.parquet`.
- **Downstream consumers:** 10–14.
- **Required src modules:** `src/calculations/fouling.py`, `src/models/degradation_curves.py`, `src/validation/fouling_reliability.py`.
- **Configuration files:** `config/fouling.yaml`.
- **Unit tests:** Physical rate invariant; initiation boundary; recovery split; noisy-run exclusion; synthetic linear/asymptotic cases.
- **Completion criteria:** Current status never silently inherits an unreliable rate; every rate has confidence and exclusion reason.
- **Engineering approval required:** Heat-transfer/process engineer approves indicator interpretation and reliability gates.

### 10_cleaning_event_detection

- **Primary analytical question:** When did cleaning, shell switching, TAM, or unexplained recovery occur, and how confident is each event?
- **Business purpose:** Reconstruct missing cleaning history while keeping inferred events distinguishable from confirmed work.
- **Upstream stage:** 05, 08, and 09.
- **Input datasets:** Operating modes/runs; clean-reference/performance; fouling daily; shutdown/TAM candidates; optional maintenance log.
- **Required columns:** `event_id`, `event_timestamp`, `hx_id`, `event_type`, `event_source`, `confidence_tier`, `u_recovery`, `q_recovery_kw`, `cit_recovery`, `confirmed_by_user`, `evidence`.
- **Primary key:** `event_id`.
- **Time grain:** Event.
- **Calculations:** Change-point/recovery detection; simultaneous-HX TAM detection; mode-switch evidence; pre/post event study; confidence scoring.
- **Engineering checks:** Whole-train TAM recovery is not assigned to one HX; event windows exclude shutdown instability; confirmed logs override inference without deleting evidence.
- **Required summary tables:** Cleaning-event register; event counts/confidence by HX; measured recovery summary.
- **Required diagnostic plots:** Full-history event timeline; pre/post recovery event study; confidence/evidence matrix; representative switch event; representative TAM event.
- **Output datasets:** `data/gold/cleaning_events.parquet`; `data/gold/cleaning_event_effects.parquet`.
- **Downstream consumers:** 08 reference updates, 11–14.
- **Required src modules:** `src/events/cleaning_detection.py`, `src/events/change_points.py`, `src/events/event_study.py`.
- **Configuration files:** `config/cleaning_events.yaml`, `config/tam_periods.yaml`.
- **Unit tests:** TAM attribution; positive/negative recovery confidence; overlapping event de-duplication; confirmed-log precedence.
- **Completion criteria:** Every event is confirmed or explicitly inferred with evidence and confidence.
- **Engineering approval required:** Maintenance and operations review event register.

### 11_cit_and_furnace_impact

- **Primary analytical question:** How does CPHT degradation affect CIT, furnace duty, fuel gas, and operating headroom?
- **Business purpose:** Translate HX fouling into furnace risk and energy consequences.
- **Upstream stage:** 04–10.
- **Input datasets:** Validated furnace tags; HX fouling/performance; cleaning events; crude properties; engineering limits.
- **Required columns:** `timestamp`, `cit_measured`, `cit_expected`, `cit_deficit_calculated`, `furnace_duty_calculated`, `fuel_gas_measured`, `fuel_gas_expected`, constraint values/headroom, `impact_method`, `impact_confidence`.
- **Primary key:** `timestamp`; HX attribution table uses `timestamp`, `hx_id`.
- **Time grain:** Daily and event summary.
- **Calculations:** CIT deficit; chronological/causal-safe sensitivity; furnace heat-duty balance; fuel-gas cross-check; headroom to COT, FG, pressure, skin, stack, O2 and draft limits.
- **Engineering checks:** Same-timestamp variables are labeled explanatory, not forecasts; terminal HX direct-CIT relationship handled separately; all limits loaded from config; pass-level skin constraints retained.
- **Required summary tables:** Current furnace headroom; HX-to-CIT impact estimates; cleaning-event furnace response.
- **Required diagnostic plots:** CIT vs total fouling history; furnace duty/fuel gas vs CIT; constraint headroom dashboard plot; pass skin-temperature history; event-study response.
- **Output datasets:** `data/gold/cit_furnace_daily.parquet`; `data/gold/hx_cit_impact.parquet`; `data/gold/furnace_constraint_status.parquet`.
- **Downstream consumers:** 12–15.
- **Required src modules:** `src/calculations/furnace.py`, `src/models/cit_impact.py`, `src/validation/leakage.py`.
- **Configuration files:** `config/engineering_limits.yaml`, `config/furnace.yaml`.
- **Unit tests:** Headroom calculations; limit direction; four-pass skin logic; lag enforcement; fuel-gas formula hand checks.
- **Completion criteria:** Impact estimates are separated into measured, modeled, and assumed; no predictive claim uses same-timestamp leakage.
- **Engineering approval required:** Furnace and process engineers.

### 12_forecasting

- **Primary analytical question:** What are the future trajectories and uncertainty for fouling, CIT, and time-to-limit?
- **Business purpose:** Provide early warning and planning horizons.
- **Upstream stage:** 09–11.
- **Input datasets:** Fouling daily/runs; current clean baselines; CIT/furnace daily; crude scenarios; operating constraints.
- **Required columns:** `forecast_origin`, `horizon_timestamp`, `hx_id`, `target_name`, `prediction`, `lower_bound`, `upper_bound`, `baseline_prediction`, `model_name`, `validation_status`.
- **Primary key:** `forecast_origin`, `horizon_timestamp`, `hx_id`, `target_name`, `model_version`.
- **Time grain:** Daily horizon, with 30/60/90/182-day summaries.
- **Calculations:** Persistence/constant-rate baselines; degradation curves; walk-forward forecasts; scenario assumptions; probabilistic threshold crossing.
- **Engineering checks:** Chronological validation; no random split; no future crude unless explicitly scenario-based; model must beat or defer to baseline; uncertainty coverage reported.
- **Required summary tables:** Model comparison by target/horizon; current threshold-crossing forecast; scenario assumptions.
- **Required diagnostic plots:** Walk-forward backtest; actual-vs-forecast by horizon; uncertainty calibration; representative forecast cones; error vs horizon.
- **Output datasets:** `data/gold/forecasts.parquet`; `data/gold/threshold_risk.parquet`; versioned model registry.
- **Downstream consumers:** 13–15.
- **Required src modules:** `src/models/fouling_forecast.py`, `src/models/cit_forecast.py`, `src/models/baselines.py`, `src/models/forecast_validation.py`.
- **Configuration files:** `config/forecasting.yaml`, `config/scenarios.yaml`.
- **Unit tests:** Split chronology; leakage feature audit; baseline fallback; interval ordering; threshold probability bounds.
- **Completion criteria:** Every deployed forecast passes baseline and leakage gates or is clearly labeled engineering extrapolation.
- **Engineering approval required:** Process engineer approves horizons and scenario assumptions; data science owner approves validation.

### 13_cleaning_prioritization

- **Primary analytical question:** Which HX should be cleaned, when, and by which feasible method?
- **Business purpose:** Convert condition, risk, forecast, and logistics into an actionable priority.
- **Upstream stage:** 09–12.
- **Input datasets:** Current fouling; cleaning events; forecasts; HX-CIT impact; furnace constraints; bypass/swap/TAM capability.
- **Required columns:** `decision_date`, `hx_id`, `priority_rank`, `priority_score`, `condition_score`, `consequence_score`, `urgency_score`, `feasibility_class`, `recommended_window`, `recommendation_confidence`, `reason_codes`.
- **Primary key:** `decision_date`, `hx_id`, `scenario_id`.
- **Time grain:** Decision snapshot and planning window.
- **Calculations:** Transparent multi-criteria ranking; feasibility filtering; network interaction; constrained scheduling; baseline “worst condition first” comparison.
- **Engineering checks:** TAM-only and swap-capable constraints; crew/resource limits; CIT/furnace limits; inherited partner rates explicitly marked; no unreliable rate silently used.
- **Required summary tables:** Ranked decision table; feasible schedule; blocked/deferred HX register.
- **Required diagnostic plots:** Priority decomposition; risk-vs-effort matrix; schedule/Gantt; constraint utilization; baseline-vs-optimizer comparison.
- **Output datasets:** `data/gold/cleaning_priority.parquet`; `data/gold/cleaning_schedule.parquet`; `data/gold/optimization_diagnostics.parquet`.
- **Downstream consumers:** 14 and 15.
- **Required src modules:** `src/optimization/priority.py`, `src/optimization/scheduler.py`, `src/optimization/constraints.py`.
- **Configuration files:** `config/cleaning_constraints.yaml`, `config/priority_weights.yaml`.
- **Unit tests:** Feasibility classes; TAM constraints; crew caps; limit enforcement; deterministic ranking; optimizer-vs-baseline.
- **Completion criteria:** One authoritative priority and one authoritative schedule are produced with reason codes and constraint diagnostics.
- **Engineering approval required:** Operations, maintenance, process, and furnace engineering.

### 14_economic_evaluation

- **Primary analytical question:** What is the expected value, cost, payback, and uncertainty of each cleaning plan?
- **Business purpose:** Ensure recommendations are economically justified without overstating independent CIT gains.
- **Upstream stage:** 10–13.
- **Input datasets:** Cleaning priority/schedule; measured event effects; HX-CIT impact; furnace/fuel relationship; approved costs and prices.
- **Required columns:** `decision_date`, `hx_id`, `scenario_id`, `cit_gain`, `fuel_saving`, `annual_saving`, `cleaning_cost`, `downtime_cost`, `net_present_value`, `payback_days`, `uncertainty_low`, `uncertainty_high`, `value_source`.
- **Primary key:** `decision_date`, `hx_id`, `scenario_id`.
- **Time grain:** Decision/scenario.
- **Calculations:** Fuel savings; cleaning cost; downtime; payback; annualized and NPV views; uncertainty/scenario analysis; network interaction discount.
- **Engineering checks:** TAM effects not attributed per HX; measured gain preferred; modeled gain calibrated and labeled; additive HX benefits bounded; units and price dates explicit.
- **Required summary tables:** Per-HX economics; plan/scenario economics; assumption sensitivity.
- **Required diagnostic plots:** Cost-benefit quadrant; payback ranking; tornado/sensitivity plot; cumulative plan value; measured-vs-modeled gain comparison.
- **Output datasets:** `data/gold/economic_evaluation.parquet`; `data/gold/economic_assumptions_snapshot.parquet`.
- **Downstream consumers:** 15.
- **Required src modules:** `src/economics/benefits.py`, `src/economics/costs.py`, `src/economics/scenarios.py`.
- **Configuration files:** `config/economics.yaml`.
- **Unit tests:** Hand-calculated plant formula; unit conversion; no double counting; cost override validation; uncertainty bounds.
- **Completion criteria:** Every monetary result identifies price date, formula, source type, and uncertainty.
- **Engineering approval required:** Economics/energy management plus maintenance for cost assumptions.

### 15_dashboard_dataset

- **Primary analytical question:** What approved, stable, minimal datasets does the dashboard need to support decisions?
- **Business purpose:** Publish one governed interface without recreating engineering logic in the UI.
- **Upstream stage:** 02 and 09–14.
- **Input datasets:** Approved gold tables; asset/tag labels; run manifest; approval records.
- **Required columns:** Dataset-specific schemas plus `snapshot_id`, `generated_at`, `pipeline_run_id`, `schema_version`, `approval_status`, `data_freshness`.
- **Primary key:** `snapshot_id` plus entity key.
- **Time grain:** Current snapshot, daily history, event, and forecast horizon as appropriate.
- **Calculations:** Presentation-only joins, rounding, labels, compact downsampling, status categories already computed upstream.
- **Engineering checks:** No dashboard-side Q, CIT, fuel, economics, priority, or limit calculations; only approved rows published; measured/calculated/inferred labels retained.
- **Required summary tables:** Dataset catalog; schema/freshness manifest; publication approval table.
- **Required diagnostic plots:** Publication completeness/freshness chart; schema validation summary; payload-size trend.
- **Output datasets:** `data/published/dashboard/*.parquet`; controlled JSON exports; `dashboard_manifest.json`.
- **Downstream consumers:** Web dashboard and APIs only.
- **Required src modules:** `src/publish/dashboard.py`, `src/publish/schemas.py`, `src/publish/serialization.py`.
- **Configuration files:** `config/dashboard_datasets.yaml`, `config/schema_versions.yaml`.
- **Unit tests:** JSON/Parquet schema; referential integrity; no prohibited raw/intermediate fields; snapshot consistency; payload bounds.
- **Completion criteria:** Dashboard can be rebuilt from Stage 15 outputs alone and contains no core engineering formulas.
- **Engineering approval required:** Product owner and engineering approvers sign the snapshot.

### 16_end_to_end_validation

- **Primary analytical question:** Is one complete pipeline run internally consistent, reproducible, leakage-safe, physically plausible, and ready to publish?
- **Business purpose:** Prevent mixed-generation or unapproved results from reaching users.
- **Upstream stage:** 00–15.
- **Input datasets:** All manifests, stage outputs, schemas, model registry, tests, approval records.
- **Required columns:** `validation_check_id`, `run_id`, `stage_id`, `check_type`, `status`, `severity`, `evidence_path`, `owner`, `waiver_id`.
- **Primary key:** `run_id`, `validation_check_id`.
- **Time grain:** Pipeline run.
- **Calculations:** Row-count reconciliation, freshness, source/config hashes, schema checks, physical invariants, leakage audit, baseline comparison, reproducibility comparison.
- **Engineering checks:** All mandatory approvals current; no unapproved limit; no mixed snapshot; no reliable positive fouling rate; no forecast without baseline; no dashboard calculation duplication.
- **Required summary tables:** Release-gate scorecard; unresolved findings; stage lineage manifest.
- **Required diagnostic plots:** Stage row-count waterfall; freshness timeline; model-vs-baseline scorecard; physical-check violations; approval coverage.
- **Output datasets:** `artifacts/validation/end_to_end_validation.parquet`; signed release manifest; approved dashboard snapshot pointer.
- **Downstream consumers:** Release/deployment process.
- **Required src modules:** `src/validation/end_to_end.py`, `src/validation/schemas.py`, `src/validation/leakage.py`, `src/validation/approvals.py`.
- **Configuration files:** `config/release_gates.yaml`, all schema and approval configs.
- **Unit tests:** Validation failure propagation; stale artifact detection; mixed-run rejection; approval expiry; deterministic rerun comparison.
- **Completion criteria:** Every critical check passes; warnings have owners/waivers; approved snapshot is atomically published.
- **Engineering approval required:** Final joint approval by project owner, process, furnace, operations, maintenance, and data-science owner.

## 5. Cross-stage approval gates

| Gate | Required before | Approval |
|---|---|---|
| G1 Requirements | Stage 02 | Business/process/furnace/maintenance |
| G2 Tags and topology | Stage 03 | Instrument/process/operations |
| G3 Data quality rules | Stage 05 | Instrument/process |
| G4 Operating modes | Stage 07 | Operations/process |
| G5 Heat-duty and normalization formula | Stage 08 | Heat-transfer/process |
| G6 Clean reference | Stage 09 | Heat-transfer/process |
| G7 Fouling indicator/rate | Stage 10 | Heat-transfer/process |
| G8 Cleaning event register | Stage 11/14 | Maintenance/operations |
| G9 Furnace impact and limits | Stage 12/13 | Furnace/process |
| G10 Forecast validation | Stage 13 | Data science/process |
| G11 Priority and schedule | Stage 14 | Operations/maintenance/process/furnace |
| G12 Economics | Stage 15 | Economics/energy/maintenance |
| G13 Release | Dashboard publication | Joint release board |

## 6. Publication and failure behavior

- A run writes to a new `run_id` directory.
- No stage mutates a prior stage's dataset.
- Failed stages leave their run unpublished.
- Stage 15 writes a candidate dashboard snapshot.
- Stage 16 either atomically promotes that snapshot or rejects it.
- The dashboard displays the published run ID, generation time, data end date, approval state, and warnings.

