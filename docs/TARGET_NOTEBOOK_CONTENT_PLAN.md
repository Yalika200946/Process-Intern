# Target Notebook Content Plan

## Notebook template

Every target notebook should use this order:

1. Title and one-sentence analytical question.
2. Business decision supported.
3. Declared input/output contract:
   - datasets and schema versions;
   - primary key and time grain;
   - configuration files;
   - upstream and downstream stages.
4. Assumptions, limitations, measured/calculated/inferred definitions.
5. Load approved stage inputs through `src/`.
6. Data/schema validation summary.
7. Main analysis.
8. Three to six primary diagnostic figures where relevant.
9. One to three summary tables.
10. Engineering checks and approval status.
11. Output write confirmation, row counts, hashes, and manifest link.
12. Completion checklist.

Notebooks must display only summary plots and representative cases. Repeated per-HX figures are generated through reusable plotting functions and saved under `reports/figures/<stage>/per_hx/`.

## Stage-by-stage content

### 00_project_setup

- **Question:** Is this run environment reproducible and ready?
- **Summary tables (2):** Environment/dependency readiness; configuration and approval register.
- **Primary figures:** None.
- **Notebook content:** Resolve paths, load config, create run context, show hashes and missing approvals.
- **Saved details:** Run manifest and logs under `artifacts/`.

### 01_business_requirements

- **Question:** What decisions, limits, and acceptance tests define success?
- **Summary tables (3):** Requirement traceability; engineering-limit ownership; unresolved decisions.
- **Primary figures:** Optional requirement-coverage bar chart only.
- **Notebook content:** Render approved requirements and show gaps. No engineering calculation.

### 02_data_inventory_and_tag_mapping

- **Question:** Is every physical measurement and HX topology element mapped correctly?
- **Summary tables (3):** Tag dictionary coverage; unresolved/duplicate mappings; HX topology and sensor availability.
- **Primary figures (3):**
  1. CPHT topology with canonical asset IDs.
  2. Tag-coverage heatmap by HX and measurement type.
  3. Measured/calculated/inferred lineage map.
- **Representative cases:** E101G missing instrumentation and E112C/E113A topology.
- **Saved details:** Full topology and mapping figures under `reports/figures/02_tag_mapping/`.

### 03_data_ingestion

- **Question:** Were all source files ingested unchanged and reconciled?
- **Summary tables (3):** Source registry; row-count reconciliation; parse-error summary.
- **Primary figures (3):**
  1. Source coverage timeline.
  2. File overlap/gap timeline.
  3. Sampling-frequency distribution.
- **Notebook content:** Source hashes, schemas, parsing results. Do not clean data here.

### 04_data_quality

- **Question:** Which observations are fit for engineering analysis?
- **Summary tables (3):** Tag DQ scorecard; exclusion/imputation summary; shutdown candidate periods.
- **Primary figures (5):**
  1. Missingness heatmap.
  2. Coverage timeline for critical tags.
  3. Physical-range violation ranking.
  4. Representative raw-vs-flagged/corrected overlay.
  5. Sampling-gap distribution.
- **Representative cases:** CIT, total charge, one cold-side temperature chain, fuel gas, and one tube-skin pass.
- **Saved details:** Per-tag overlays under `reports/figures/04_data_quality/`.

### 05_time_alignment_and_operating_modes

- **Question:** Which HX was in service at each timestamp?
- **Summary tables (3):** Mode duration by HX; run register; inferred-mode confidence.
- **Primary figures (4):**
  1. Whole-train operating-mode timeline.
  2. HX service-availability heatmap.
  3. E101 branch-flow/E101G inference.
  4. E112C/E113A swap representative timeline.
- **Saved details:** Per-HX mode timelines under `reports/figures/05_operating_modes/per_hx/`.

### 06_crude_property_calculation

- **Question:** What crude properties apply to each process day?
- **Summary tables (3):** Assay/grade periods; property ranges by grade; assumed/fallback property register.
- **Primary figures (4):**
  1. Crude-grade timeline.
  2. API, SG, asphaltene and viscosity trends.
  3. Property correlation matrix.
  4. Calculated-vs-reference Cp/density checks.
- **Notebook content:** Effective dating and correlation validity, not fouling conclusions.

### 07_hx_heat_duty_calculation

- **Question:** What valid heat duty and performance does each HX deliver?
- **Summary tables (3):** Current HX performance; formula/sensor availability; invalid-calculation counts.
- **Primary figures (5):**
  1. Train heat-duty profile.
  2. HX duty distribution/ranking.
  3. Duty vs charge/load.
  4. Hot/cold energy-balance cross-check where available.
  5. Representative temperature and Q histories.
- **Representative cases:** One CPHT-1 HX, one CPHT-2 HX, terminal E113A, and a shared-meter HX.
- **Saved details:** One standardized performance dashboard per HX under `reports/figures/07_hx_performance/per_hx/`.

### 08_clean_baseline_model

- **Question:** What should each HX deliver when acceptably clean under comparable conditions?
- **Summary tables (3):** Clean-reference register; model/baseline comparison; uncertainty coverage by HX.
- **Primary figures (5):**
  1. Candidate clean windows across history.
  2. Actual vs clean-baseline prediction for representative HXs.
  3. Residuals vs charge/crude properties.
  4. Chronological validation performance.
  5. Prediction-interval calibration.
- **Representative cases:** Approved post-clean window, questionable post-TAM window, sparse HX, terminal HX.
- **Saved details:** Per-HX baseline diagnostics under `reports/figures/08_clean_baseline/per_hx/`.

### 09_fouling_analysis

- **Question:** How fouled is each HX and how reliably is it deteriorating?
- **Summary tables (3):** Current fouling status; run-level reliable rates; excluded/unreliable runs.
- **Primary figures (5):**
  1. All-HX fouling-state heatmap.
  2. Fouling-rate ranking with confidence intervals.
  3. Representative linear degradation fit.
  4. Representative asymptotic degradation fit.
  5. Reliable vs noisy/unreliable run comparison.
- **Saved details:** Standard run/fouling dashboards for every HX under `reports/figures/09_fouling/per_hx/`.

### 10_cleaning_event_detection

- **Question:** When did cleaning or recovery occur, and how confident is the evidence?
- **Summary tables (3):** Event register; confidence counts by HX/type; measured recovery summary.
- **Primary figures (5):**
  1. Full-history event timeline.
  2. Event-study aggregate recovery.
  3. Confidence/evidence matrix.
  4. Representative online switch/clean.
  5. Representative TAM event.
- **Saved details:** Per-HX event timelines and pre/post windows under `reports/figures/10_cleaning_events/per_hx/`.

### 11_cit_and_furnace_impact

- **Question:** How does CPHT degradation affect CIT and F101 operating headroom?
- **Summary tables (3):** Current furnace constraint headroom; HX-CIT impact; event-response summary.
- **Primary figures (6):**
  1. CIT and total fouling history.
  2. Furnace duty/fuel gas vs CIT.
  3. Current constraint headroom chart.
  4. Four-pass tube-skin history and limits.
  5. HX impact ranking with confidence.
  6. Cleaning event furnace-response plot.
- **Notebook content:** Separate explanatory association, event-based measurement, and forecast-safe impact estimates.

### 12_forecasting

- **Question:** What will fouling/CIT do next, with what uncertainty?
- **Summary tables (3):** Model-vs-baseline by target/horizon; threshold-risk table; scenario assumptions.
- **Primary figures (5):**
  1. Walk-forward split diagram and results.
  2. Error vs forecast horizon.
  3. Prediction-interval coverage/calibration.
  4. Representative HX fouling forecast cone.
  5. CIT/furnace headroom forecast under approved scenarios.
- **Saved details:** Forecast cone for every HX under `reports/figures/12_forecasting/per_hx/`.
- **Display rule:** Show top-risk, median-risk, and low-confidence examples only.

### 13_cleaning_prioritization

- **Question:** Which HX should be cleaned, when, and under what constraints?
- **Summary tables (3):** Authoritative priority table; feasible schedule; deferred/blocked register.
- **Primary figures (5):**
  1. Priority score decomposition.
  2. Risk-vs-effort matrix.
  3. Cleaning schedule/Gantt.
  4. Constraint utilization over time.
  5. Optimizer vs simple baseline comparison.
- **Notebook content:** One ranking and one schedule only; alternatives are diagnostics, not competing outputs.

### 14_economic_evaluation

- **Question:** Is the cleaning plan economically worthwhile under uncertainty?
- **Summary tables (3):** Per-HX economics; total plan/scenario economics; assumptions and price dates.
- **Primary figures (5):**
  1. Cost-benefit quadrant.
  2. Payback ranking.
  3. Tornado/sensitivity chart.
  4. Cumulative plan value by time.
  5. Measured-vs-modeled CIT gain comparison.
- **Notebook content:** Explicitly display upper-bound/additivity caveats and uncertainty.

### 15_dashboard_dataset

- **Question:** Are the approved dashboard datasets complete, coherent, and presentation-ready?
- **Summary tables (3):** Dataset catalog/schema; freshness manifest; publication approval register.
- **Primary figures (3):**
  1. Dataset completeness/freshness.
  2. Payload-size trend.
  3. Schema-validation pass/fail summary.
- **Notebook content:** Show sample records and schema—not recreate dashboard calculations.

### 16_end_to_end_validation

- **Question:** Can this exact run be safely published?
- **Summary tables (3):** Release-gate scorecard; unresolved findings/waivers; full lineage manifest.
- **Primary figures (5):**
  1. Stage row-count waterfall.
  2. Artifact freshness timeline.
  3. Model-vs-baseline scorecard.
  4. Physical-check violation summary.
  5. Approval coverage by stage.
- **Notebook content:** Fail closed. Publication occurs only after all critical checks pass.

## Plot-generation rules

1. All plot data comes from the current stage's declared inputs or outputs.
2. Plot functions live under `src/` or a dedicated reporting module, not copied across notebooks.
3. Every saved plot includes run ID, data end date, units, and measured/calculated/inferred legend where relevant.
4. Per-HX plots use a standard layout and axis convention.
5. The notebook embeds at most:
   - one fleet-level overview;
   - three or four representative HX cases;
   - one failure/low-confidence example.
6. Full per-HX sets are linked, not embedded repeatedly.
7. Diagnostic plots are not dashboard products unless Stage 15 explicitly approves them.

## Summary-table rules

- Tables are written as Parquet under `reports/tables/` when they are part of validation evidence.
- Tables include units in column metadata or explicit unit columns.
- Rankings include score components and reason codes, not only a final rank.
- Empty or unavailable results are explicit and never replaced with zero.
- Every table displays its source run ID and schema version.

