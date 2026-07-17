# Current CPHT Pipeline Dependency Map

## Scope and interpretation

This document records the pipeline as implemented on 2026-07-16. It is a current-state map, not a proposed architecture. It was derived from notebook cells, Python source, `pipeline/run_all.py`, dashboard fetch calls, and explicit file reads/writes.

- **Confirmed dependency**: an actual import, read, write, subprocess invocation, or dashboard fetch is present in code.
- **Inferred dependency**: historical intent, saved notebook output, naming, or documentation indicates a relationship, but the active code does not enforce it.
- **Reproducible** means reproducible only in the expected project environment with the external plant-data directory and required packages available. It does not mean the result has been independently validated.
- The detailed row-level record is in [NOTEBOOK_DEPENDENCY_MATRIX.csv](NOTEBOOK_DEPENDENCY_MATRIX.csv).
- The visual data-flow view is in [CURRENT_PIPELINE_GRAPH.md](CURRENT_PIPELINE_GRAPH.md).

## Executive summary

The active production chain is:

1. `01_data_cleaning.ipynb`
2. `02_feature_engineering.ipynb`
3. `03_operating_state_classification.ipynb`
4. `pipeline/compute_fouling_rate.py`
5. `04_fouling_rate_estimation.ipynb`
6. `05_fouling_cit_sensitivity.ipynb`
7. `06_fouling_rate_forecast.ipynb`
8. `07_time_to_clean_prediction.ipynb`
9. `08_cleaning_priority_ranking.ipynb`
10. `09_cit_model_feature_matrix.ipynb`
11. `10_cit_model_benchmark.ipynb`
12. `11_cit_shap_importance.ipynb`
13. `12_economic_delta_cit.ipynb`
14. `13_cit_forecast_export.ipynb`
15. A post-processing chain that creates the dashboard JSON artifacts.

The chain is not a clean directed acyclic data pipeline:

- ~~Notebook 02 writes a preliminary `Fouling_Rate_By_Run.csv`, which `compute_fouling_rate.py` later overwrites.~~ Resolved (Phase 1 item A1): notebook 02 no longer writes this file; `compute_fouling_rate.py` is the sole writer.
- `compute_fouling_rate.py` still patches `Feature_calculated.csv` in place (an upstream feature table notebook 02 also writes) — this is a genuine intermediate-reader case (notebook 03 reads notebook 02's uncorrected version to build `Operating_State.csv`, which the correction itself depends on), so the file can't have a single writer. Mitigated instead with a `fouling_baseline_corrected` lineage column (Phase 1 item A2) so a reader can tell which version they have.
- Notebook 13 writes `model_metrics.json`; `gen_honest_metrics.py` overwrites it.
- Notebook 13 writes `forecast_6mo.json`; `add_forecast_intervals.py` mutates it.
- The backend can execute notebook 16 in place and rewrite dashboard override/output files.
- The dashboard performs additional economic and furnace calculations in browser code instead of only displaying approved tables.

No true file-level circular dependency was confirmed in the batch chain. There is, however, a **runtime feedback loop**:

`dashboard inputs → backend override JSON → notebook 16/network optimizer → cleaning_plan.json → dashboard`.

## Data locations

### External raw and processed data

Most plant data is outside the repository:

`C:\Desktop\Bangchak Internship 2026\Data`

The path is sometimes read through `CPHT_DATA_DIR`, but `pipeline/run_all.py` hard-codes the Windows location. Important external inputs include:

- Raw process historian Excel
- Raw crude assay Excel
- Bypass/cleaning-capability Excel
- Cleaned and feature CSVs produced by notebooks

### Repository outputs

- `outputs/*.csv`: model/ranking/economic outputs from notebooks 09–13.
- `models/*`: XGBoost, Random Forest, LSTM, scaler, feature-list, and clean-baseline artifacts.
- `dashboard/data/*.json`: live dashboard interface.
- `figures/**`: generated analytical plots.
- `dashboard/data/backup_*`: timestamped output snapshots.

The active pipeline uses CSV rather than Parquet for processed analytical data.

## Stage map

| Stage | Producers | Primary outputs | Primary consumers |
|---|---|---|---|
| Raw profiling | Notebooks 00 process and 00 crude | Crude profile CSV; figures | Notebook 01; human review |
| Cleaning and assay merge | Notebook 01 | Cleaned process, process-with-crude, DQ score | Notebooks 02–05, model feature builder, exporters |
| Feature engineering | Notebook 02 | Feature table; preliminary run rates | Notebook 03; rate recomputation; correlation/PCA; PHM/exporters |
| Operating-state resolution | Notebook 03 | `Operating_State.csv` | Authoritative rate computation; notebooks 04 and 06 |
| Authoritative fouling calculation | `compute_fouling_rate.py` | Mutated feature table; authoritative run-rate table | Notebooks 04, 06–08, PHM, economics, optimization |
| Q/fouling calculations | Notebooks 04–05 | Feature Q, rate ranking, Q–CIT sensitivity | Notebooks 06–08; end-of-run/economics |
| Fouling forecasting | Notebooks 06–07 | Deviation signals; time-to-clean | Notebook 08; notebook 13; PHM; end-of-run |
| Engineering priority | Notebook 08 | Engineering and legacy priority CSVs | Engineering-priority exporter; notebook 16 |
| CIT modeling | Notebooks 09–11 | Priority tables; models; metrics; SHAP ranking | Notebooks 12–13; honest-metrics exporter |
| Economic delta-CIT | Notebook 12 | Clean-baseline model; delta-CIT tables; sandbox JSON | Economics/dashboard; diagnostic notebook |
| Forecast/dashboard export | Notebook 13 | Core dashboard JSONs; recommendation CSV | Dashboard; post-processors |
| PHM and evidence | Pipeline exporters | RUL, reliability, drivers, history, evidence | Dashboard; optimization |
| Optimization | Schedulers and notebook 16 | Schedule and integrated plan JSONs | Dashboard |

## Explicit notebook contracts

The current notebooks generally expose contracts through file I/O, but not all have a formal schema. No notebook uses another notebook's live Python variables as its intended interface. Their interface is disk files. This satisfies the no-memory-interface rule in intent, with these caveats:

- Notebook 09 duplicates feature-building logic later centralized in `cpht_features.py`.
- Saved output cells can make a notebook appear complete even when an upstream file has changed.
- Notebook execution in place means notebook files contain generated execution state.
- Notebook 16 may be regenerated from `_build_cleaning_plan_notebook.py`, creating two editable sources.

## Schema validation

Schema validation is incomplete:

- `backend/server.py` validates required uploaded tags and raw Excel shape.
- `tests/test_dashboard_schema.py` checks selected keys in a few outputs.
- Some notebooks perform assertions or plausibility checks.
- Most CSV and JSON outputs have no versioned schema or manifest.
- Tests skip when local artifacts are absent.
- No single run ID, source hash, schema version, or freshness manifest ties all dashboard artifacts together.

## Overwrites and duplicate outputs

| Output | First writer | Later writer/mutator | Risk |
|---|---|---|---|
| `Fouling_Rate_By_Run.csv` | `compute_fouling_rate.py` (sole writer as of Phase 1 item A1) | n/a | Resolved |
| `Feature_calculated.csv` | Notebook 02 | `compute_fouling_rate.py` | Intentional (see above); `fouling_baseline_corrected` column added Phase 1 item A2 so the two versions are distinguishable |
| `model_metrics.json` | ~~Notebook 13~~ `gen_honest_metrics.py` (sole writer as of Phase 1 item A3) | n/a | Resolved: notebook 13 no longer writes this file at all |
| `forecast_6mo.json` | Notebook 13 (interval logic folded in, Phase 1 item A4) | n/a | Resolved: `add_forecast_intervals.py` is superseded and no longer invoked by `run_all.py` |
| `cleaning_plan.json` | Notebook 16 | Notebook 16 via backend recomputation | **Not a defect** (Phase 1 item A5 review): both "writes" are the same notebook cell (full regeneration each time); `backend/server.py`'s `/api/recompute-plan` re-executes that notebook via `nbconvert --execute --inplace` with different override-JSON inputs, which is legitimate interactive recomputation, not a duplicate-writer bug. No code change needed. |
| Override JSONs | Dashboard/backend | Backend deletes or rewrites them | Runtime state is mixed with approved analytical outputs |

Duplicated or competing outputs include:

- `Cleaning_Priority_Ranking.csv`
- `Engineering_Priority_Score.csv`
- `hx_cleaning_priority.csv`
- `hx_Q_cleaning_priority.csv`
- `hx_Q_cleaning_priority_v2.csv`
- `hx_ranking.json`
- `engineering_priority.json`
- `cleaning_schedule.json`
- `cleaning_schedule_v2.json`
- `cleaning_plan.json`

These are not identical schemas and answer different variants of “what should be cleaned first,” but the distinction is not enforced by a central data contract.

## Orphans and obsolete branches

### Active but outside the production chain

- `_eda_crude_assay.ipynb` (renamed from `00_data_prep_crude_assay.ipynb`, Phase 1): required when the crude profile must be rebuilt, but absent from `run_all.py`.
- `_eda_process_control.ipynb` (renamed from `00_data_prep_process_control.ipynb`): EDA only.
- `_eda_correlation_and_pca.ipynb` (renamed from `02b_correlation_and_pca.ipynb`): exploratory analysis only.
- `15_pipeline_diagnostic_audit.ipynb`: diagnostic consumer only.
- `_diagnostic_solver_comparison.ipynb` (renamed from `16b_optimizer_solver_comparison.ipynb`): offline optimizer verification.

### Archived or obsolete notebooks

- `_archive_2026-07-12/01_case_operate_state.ipynb`
- `_archive_2026-07-12/2_correlation.ipynb`
- `_archive_2026-07-12/2_pca.ipynb`
- `_archive_2026-07-12/test_output.ipynb`
- `_archive_2026-07-12/scratch_fouling/test_features.ipynb`
- `_archive_2026-07-12/scratch_fouling/test_fouling.ipynb`
- `_archive_2026-07-12/scratch_fouling/test_models.ipynb`

They are not called by `run_all.py` or active pipeline scripts.

### Legacy Python branch

`src/core*.py` and `src/utils/*.py` form an older generic furnace-ML framework. No active CPHT notebook or pipeline script imports them. Current reusable CPHT logic instead resides in `notebooks/*.py`.

## Dashboard dependency boundary

The dashboard reads `dashboard/data/*.json`; it does not directly fetch the external CSVs or Excel files. However:

- `dashboard/index.html` calculates CIT deficit, fuel-gas reduction, CO2, payback, and cumulative economics in browser code.
- It contains hard-coded engineering/economic defaults.
- `backend/server.py` reads uploaded raw or cleaned data and writes intermediate/runtime files.
- The “quick update” endpoint refreshes topology/furnace data only, so the dashboard can combine a new topology with old rankings and forecasts.

Therefore, the browser does not read raw plant data directly, but the dashboard application is not a pure approved-output renderer.

## Model traceability

| Artifact | Training producer | Training input traceability | Active use |
|---|---|---|---|
| `xgb_cit_model.joblib` | Notebook 10 | Traceable to `cpht_features.build_cit_feature_matrix`, but no embedded dataset hash/run ID | SHAP and diagnostic use |
| `rf_cit_model.joblib` | Notebook 10 | Same limitation | SHAP cross-check |
| `lstm_cit_model.keras` | Notebook 10 | Same limitation; scaler artifact is separate | Permutation-importance cross-check |
| `lstm_scalers.joblib` | Notebook 10 | No source-data fingerprint | Notebook 11 |
| `feature_columns.joblib` | Notebook 10 | Feature names only, no schema version | Notebook 11 and diagnostic notebook |
| `clean_baseline_cit_model.joblib` | Notebook 12 | Clean-window assumptions recorded in code, no source hash | Counterfactual sandbox/economic support |

The model-producing notebooks can be identified, but the exact historical dataset used for an existing binary artifact cannot be proven from the artifact alone.

## Reproducibility assessment

The pipeline is conditionally reproducible, not fully reproducible:

- Positive: notebooks pass data through files rather than hidden memory; dependencies are pinned; orchestration order exists; baselines and some physical checks exist.
- Negative: external data is not versioned with outputs; notebook execution mutates notebooks; post-processors overwrite earlier outputs; processed data is CSV; no atomic publish; some paths are hard-coded; full dependencies are not installed in the default Docker image; active model artifacts lack lineage metadata.

## Current-state conclusions

1. The authoritative fouling-rate step is `pipeline/compute_fouling_rate.py`, not the preliminary rate section in notebook 02.
2. The active dashboard ranking source for engineering priority is `engineering_priority.json`; the integrated cleaning plan is `cleaning_plan.json`.
3. Notebook 13 is a core exporter but does not produce the final authoritative model-metrics or forecast schema by itself.
4. The batch pipeline has no confirmed circular file dependency, but the interactive dashboard creates a controlled feedback loop.
5. The most serious unresolved dependency conflict is the duplicate E112C topology in `cpht_config.py` and `cpht_features.py`.

## Ranking/score traceability (Phase 2, added 2026-07-17)

There is exactly **one** independent computation of HX cleaning-priority
ranking in the active pipeline. Every other ranking-shaped file is a
passthrough or a superseded prototype, not a second independent method —
this table exists so that question doesn't need to be re-derived by reading
code every time.

| File | Producer | Independent computation or passthrough? | Status |
|---|---|---|---|
| `Data/Engineering_Priority_Score.csv` | Notebook 08 §4, `engineering_priority_score = rank_norm(probability_score * consequence_score / effort_penalty)` | **Independent — the only real computation** | Authoritative |
| `dashboard/data/engineering_priority.json` | `pipeline/export_engineering_priority.py` | Passthrough of `Engineering_Priority_Score.csv` + `priority_rank` | Authoritative (primary dashboard/optimizer ranking source) |
| `outputs/hx_Q_cleaning_priority_v2.csv` | Notebook 11 §17 | Passthrough (`priority_v2['priority_score'] = engineering_priority_score`), adds `cit_shap_importance` as an extra informational column only | Reference (SHAP attribution), not an alternate ranking |
| `dashboard/data/hx_ranking.json` | Notebook 13 §5, from `hx_Q_cleaning_priority_v2.csv` | Passthrough of the same score, two hops removed from notebook 08 | Should always equal `engineering_priority.json`'s values for the same pipeline run — see `pipeline/export_engineering_priority.py`'s consistency check (Phase 2 Part F) for what happens when a partial rerun breaks that |
| `dashboard/data/cleaning_plan.json` | Notebook 16 §10 | Passthrough of `engineering_priority.json`'s score as primary sort key; notebook 16's own `priority_score`/`risk_mult` (net-saving × risk multiplier) is a **secondary tie-breaker and SLSQP scheduler input only**, never a replacement rank | Authoritative (cleaning-plan tab) |
| `outputs/hx_cleaning_priority.csv` (v1) | Original `09_cit_model_feature_matrix.ipynb` prototype | Independent, but superseded — naive equal-weight blend, documented as producing wrong results (e.g. E113A undersold, E101AB overstated) | Superseded; only used by `15_pipeline_diagnostic_audit.ipynb` for a v1-vs-v2 comparison plot, not consumed by the dashboard or notebook 16 |

**Practical rule:** if you need to know "is this the real ranking number,"
trace it back through this table to `Engineering_Priority_Score.csv` — if a
file isn't in this table's chain, it isn't part of the authoritative
ranking.

