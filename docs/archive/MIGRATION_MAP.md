# Migration Map — 2026-07-17 restructuring pass

**Status:** CURRENT

Authoritative old-path → new-path record for the repository restructuring
described in this session. Scope: move shared engineering/modeling code
out of `notebooks/*.py` into a proper `src/` package, archive confirmed-dead
legacy code, harden the backend upload path, add an additive cleaning-event
status taxonomy, and clean up `docs/`. No formula, threshold, or engineering
assumption changed. No notebook was executed in place. See
`docs/UNRESOLVED_ENGINEERING_DECISIONS.md` for what remains open.

## Notebook subfolder moves — EDA / diagnostics (2nd pass, same day)

Clean 1:1 renames, no content change, into the `notebooks/eda/` and
`notebooks/diagnostics/` subfolders.

| Old path | New path |
|---|---|
| `notebooks/_eda_crude_assay.ipynb` | `notebooks/eda/crude_assay_exploration.ipynb` |
| `notebooks/_eda_process_control.ipynb` | `notebooks/eda/process_control_exploration.ipynb` |
| `notebooks/_eda_correlation_and_pca.ipynb` | `notebooks/eda/correlation_and_pca.ipynb` |
| `notebooks/_diagnostic_solver_comparison.ipynb` | `notebooks/diagnostics/solver_comparison.ipynb` |

`notebooks/_build_solver_comparison_notebook.py`'s output path was updated
to match; not re-run (would regenerate/execute the notebook).

## Notebook subfolder moves — production (3rd pass, same day)

`notebooks/production/` introduced per user request, mapping the existing
13-notebook production chain onto an 11-name target list plus 2 extra
numbered files that had no slot in that list (see the mapping-proposal
discussion in conversation — not duplicated here). No notebook content was
changed, split, or merged; every move below is a straight rename. Two
targets from the requested list (`06_cleaning_event_validation.ipynb`,
`11_end_to_end_validation.ipynb`) had no current source notebook and were
created as header-only placeholders (status: NOT IMPLEMENTED), per explicit
instruction not to author new analysis content in this pass.

| Old path | New path | Notes |
|---|---|---|
| `notebooks/01_data_cleaning.ipynb` | `notebooks/production/01_data_quality.ipynb` | |
| `notebooks/03_operating_state_classification.ipynb` | `notebooks/production/02_operating_modes.ipynb` | |
| `notebooks/02_feature_engineering.ipynb` | `notebooks/production/03_hx_performance.ipynb` | |
| `notebooks/06_fouling_rate_forecast.ipynb` | `notebooks/production/04_clean_baseline.ipynb` | closest existing fit: builds the clean-baseline model + deviation signal |
| `notebooks/04_fouling_rate_estimation.ipynb` | `notebooks/production/05_fouling_analysis.ipynb` | |
| — (new placeholder) | `notebooks/production/06_cleaning_event_validation.ipynb` | NOT IMPLEMENTED; logic lives in `pipeline/export_cleaning_history.py` (calc-only, stays `.py`) |
| `notebooks/07_time_to_clean_prediction.ipynb` | `notebooks/production/07_forecasting.ipynb` | |
| `notebooks/08_cleaning_priority_ranking.ipynb` | `notebooks/production/08_cleaning_priority.ipynb` | |
| `notebooks/05_fouling_cit_sensitivity.ipynb` | `notebooks/production/09_cit_furnace_impact.ipynb` | |
| `notebooks/12_economic_delta_cit.ipynb` | `notebooks/production/10_economic_evaluation.ipynb` | |
| — (new placeholder) | `notebooks/production/11_end_to_end_validation.ipynb` | NOT IMPLEMENTED; closest existing coverage is `tests/test_dashboard_schema.py` and `notebooks/diagnostics/fouling_model_diagnostics.ipynb`, neither duplicated here |
| `notebooks/13_cit_forecast_export.ipynb` | `notebooks/production/12_cit_forecast_export.ipynb` | no slot in the requested 11-name list (terminal dashboard-JSON exporter); kept as an extra numbered file rather than dropped |
| `notebooks/16_cleaning_plan_optimization.ipynb` | `notebooks/production/13_cleaning_plan_optimization.ipynb` | no slot in the requested 11-name list (active SLSQP cleaning-plan optimizer, dashboard-critical); kept as an extra numbered file rather than dropped |
| `notebooks/15_pipeline_diagnostic_audit.ipynb` | `notebooks/diagnostics/fouling_model_diagnostics.ipynb` | closest fit of the two requested diagnostics names; doesn't split cleanly, kept as one file |
| — (new placeholder) | `notebooks/diagnostics/event_detection_diagnostics.ipynb` | NOT IMPLEMENTED |

**Intentionally NOT moved into `notebooks/production/`** (stay at their
original `notebooks/` root path): `09_cit_model_feature_matrix.ipynb`,
`10_cit_model_benchmark.ipynb`, `11_cit_shap_importance.ipynb` — already
documented in `ARCHIVE_CANDIDATES.md`/`SOURCE_OF_TRUTH_CANDIDATES.md` as
"reference, not canonical" (10's own finding: ML loses to a persistence
baseline). They still execute as real `pipeline/run_all.py` `CHAIN` steps
(their outputs feed `production/12_cit_forecast_export.ipynb` and
`gen_honest_metrics.py`), just not physically relocated. Also unmoved:
`14_tam_constraint_analysis.ipynb` (active `POST`-chain step, not part of
this mapping request).

**Known naming/order mismatch (documented, not fixed):** the new
`production/` filenames' leading numbers follow `TARGET_PIPELINE.md`'s
conceptual stage order (data quality → operating modes → hx performance →
...), but `pipeline/run_all.py`'s actual, validated execution order has
`03_hx_performance.ipynb` running *before* `02_operating_modes.ipynb` —
the real code dependency is the reverse of the conceptual target order
(operating-state resolution reads the feature table hx_performance
produces). Reconciling filename order with run order would mean reordering
real notebook calculation dependencies, which is a methodology change, not
a rename — out of scope here and not attempted. `run_all.py`'s `CHAIN`
list is authoritative for actual run order; see its inline comment.

References updated: `pipeline/run_all.py` (`CHAIN`, `POST`, the
post-operating-modes `compute_fouling_rate.py` hook, the terminal-notebook
check), `backend/server.py` (`/api/recompute-plan`'s notebook path),
`notebooks/_build_cleaning_plan_notebook.py` (output path),
`tests/test_pipeline_orchestration.py` (selector/path assertions).

## `src/` moves (shared modules out of `notebooks/*.py`)

| Old path | New path | Notes |
|---|---|---|
| `notebooks/cpht_config.py` | `src/domain/config.py` | HX_CONFIG, tag/group definitions |
| `notebooks/bypass_config.py` | `src/domain/bypass.py` | BYPASS_CONFIG, online_mode; gained additive `feasibility_label()` |
| `notebooks/cpht_features.py` | `src/features/heat_duty.py` | `compute_q_features`, `build_cit_feature_matrix`, etc. |
| `notebooks/crude_properties.py` | `src/features/crude_properties.py` | `cp_rho_crude` |
| `notebooks/curve_models.py` | `src/models/fouling_curves.py` | fouling curve-fit models |
| `notebooks/phm_config.py` | `src/models/phm_config.py` | PHM horizons/scenario settings (unchanged; approved-only extraction to `config/` still pending, see `ARCHIVE_CANDIDATES.md`) |
| `notebooks/cleaning_logistics.py` | `src/optimization/cleaning_logistics.py` | cleaning/bypass/TAM list export script |
| `notebooks/build_dashboard_topology.py` | `src/reporting/dashboard_topology.py` | P&ID topology export script |
| `notebooks/nb_audit.py` | `src/validation/nb_audit.py` | `robust_fouling_rate`, `data_quality_report`, kept as one file (mixed responsibility, not split this pass) |

**Backward-compat shims:** `notebooks/cpht_config.py`, `bypass_config.py`,
`cpht_features.py`, `crude_properties.py`, `curve_models.py`, `nb_audit.py`,
`phm_config.py` still exist at their old paths as one-line
`from src.<pkg>.<mod> import *` re-exports. This is deliberate: all 16
production notebooks' existing `sys.path.append(NB); from cpht_config
import ...` cells were left untouched (cannot be re-run in place to verify
an edit — see rule in the approved plan), so they keep resolving through
these shims. **Follow-up:** retire each shim the next time its notebook is
genuinely re-run/re-approved, by swapping the notebook's import cell to
`from src....` directly. `build_dashboard_topology.py` and
`cleaning_logistics.py` have no shim — nothing imports them as modules
(they're subprocess-invoked scripts only); their callers
(`pipeline/run_all.py`, `backend/server.py`) were updated directly to the
new `src/` paths.

## Fixed direct importers (no shim needed — plain `.py`, verified by import)

`pipeline/export_hx_timeseries.py`, `export_cleaning_history.py`,
`compute_fouling_rate.py`, `export_end_of_run.py`, `phm_analysis.py`,
`gen_honest_metrics.py`, `run_all.py`; `backend/server.py`;
`tests/conftest.py`, `tests/test_fouling_rate.py`.

## Archived (moved, not deleted)

| Old path | New path | Reason |
|---|---|---|
| `src/core.py` | `src/archive/core.py` | legacy generic ML framework, no active importer |
| `src/core_stateless.py` | `src/archive/core_stateless.py` | same |
| `src/core_configs.py` | `src/archive/core_configs.py` | same |
| `src/utils/configs.py`, `modelFuncs.py`, `models.py`, `prints.py`, `utilities.py` | `src/archive/utils/*` | support code for the above, no active importer |
| `src/utils/analysis.py`, `metrics.py`, `plots.py` | `src/archive/utils/*` | no active importer; flagged in `ARCHIVE_CANDIDATES.md` as worth mining for reusable plotting conventions first — not done yet |
| `dashboard/dashboard_pro.html` | `archive/dashboard_pro.html` | superseded UI, confirmed by `RUN.md`, no code reference |
| `docs/00_Requirement_and_Redesign_Plan.md`, `01_Stepwise_Execution_Plan.md` | `docs/archive/*` | superseded by `docs/02_Requirement_v2_SSOT.md` (states this explicitly) |

**Not archived despite being a candidate:** `pipeline/cleaning_scheduler.py`
— still referenced by `pipeline/run_all.py`'s POST chain as the v1 baseline
schedule; `ARCHIVE_CANDIDATES.md` says keep it until Stage 13 validation is
approved. Archiving it this pass would have broken a live pipeline step.

## Removed (empty, untracked, no history to lose)

`notebooks_v2/`, `scripts/`, `py_examples/`, `profiling/` — confirmed empty
before removal.

## Additive-only changes (no path change, listed for completeness)

- `pipeline/export_cleaning_history.py`: new `event_status()` function and
  `event_status` field in `Cleaning_Events.csv`/`cleaning_history.json`
  (CONFIRMED_TAM / SWITCH_CANDIDATE / UNEXPLAINED_RECOVERY; CONFIRMED_CLEAN
  and REJECTED_EVENT reserved, never emitted without a maintenance log).
- `src/domain/bypass.py`: new `FEASIBILITY_LABELS` / `feasibility_label()`
  (TAM_ONLY / ONLINE_PARTIAL / ONLINE_FULL / SWAP_CAPABLE) over the existing
  `online_mode`/`duty_fraction`.
- `backend/server.py`: filename sanitization (`_safe_filename`), upload
  size cap (`MAX_UPLOAD_BYTES` / `CPHT_MAX_UPLOAD_MB`), and a run-lock on
  `/api/run-full`.
- `tests/test_cleaning_event_taxonomy.py`: new regression test.

## Explicitly out of scope this pass

See `docs/MIGRATION_PLAN.md` Phase 3/4 (Parquet/medallion data layers, run
manifests, approval gates) and `docs/UNRESOLVED_ENGINEERING_DECISIONS.md`
(any formula/threshold change). Physical notebook subfolder splits
(`notebooks/production/` etc.) were considered and explicitly declined in
favor of the existing flat + `_eda_`/`_diagnostic_`/`_archive_` naming
convention.
