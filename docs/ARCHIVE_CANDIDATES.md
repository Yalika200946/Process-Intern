# Archive Candidates

**Status:** CURRENT

No file should be moved or deleted until the target pipeline reproduces approved outputs and the user gives separate approval.

## High-confidence archive candidates

### Already archived or scratch

- All files under `notebooks/_archive_2026-07-12/`.
- `notebooks/_archive_2026-07-12/scratch_fouling/`.

Reason: no active production callers; superseded or prototype logic; stale configurations.

### Notebook builders

- `scripts/_build_cleaning_plan_notebook.py` (moved from `notebooks/` 2026-07-19 so `notebooks/` holds only `.ipynb` files)
- `scripts/_build_solver_comparison_notebook.py` (moved from `notebooks/` 2026-07-19)

Reason: duplicate editable sources for generated notebooks. Preserve temporarily for provenance only.

### Legacy generic ML framework — ARCHIVED 2026-07-17

- `src/archive/core.py` (was `src/core.py`)
- `src/archive/core_stateless.py` (was `src/core_stateless.py`)
- `src/archive/core_configs.py` (was `src/core_configs.py`)
- `src/archive/utils/configs.py`, `modelFuncs.py`, `models.py`, `prints.py`, `utilities.py` (was `src/utils/*`)

Reason: no active CPHT downstream users; hidden/global conventions; old model persistence; incomplete dependencies; target pipeline uses the domain-specific `src/domain`, `src/features`, `src/models`, `src/optimization`, `src/reporting`, `src/validation` modules instead (see `docs/MIGRATION_MAP.md`).

### Superseded user interfaces and schedulers

- `archive/dashboard_pro.html` (was `dashboard/dashboard_pro.html`) — **ARCHIVED 2026-07-17**, superseded UI, no code reference.
- `pipeline/cleaning_scheduler.py` — **NOT archived**: still called from `pipeline/run_all.py`'s POST chain as the v1 baseline schedule. Keep until Stage 13 validation is approved.

## Conditional archive candidates after logic extraction

| File | Required extraction first |
|---|---|
| `notebooks/eda/process_control_exploration.ipynb` (moved 2026-07-17, was `_eda_process_control.ipynb`, originally `00_data_prep_process_control.ipynb`, Phase 1) | Inventory/DQ representative plots |
| `notebooks/eda/correlation_and_pca.ipynb` (moved 2026-07-17, was `_eda_correlation_and_pca.ipynb`, originally `02b_correlation_and_pca.ipynb`) | Selected exploratory diagnostics |
| `14_cit_model_feature_matrix.ipynb` | Any useful plotting/reference only; calculations should be rebuilt |
| `src/models/phm_config.py` (moved 2026-07-17, was `notebooks/phm_config.py`) | Approved horizon/scenario settings |
| `src/archive/utils/analysis.py` (already archived 2026-07-17, extraction still pending) | Any desired PCA/report plotting patterns |
| `src/archive/utils/metrics.py` (already archived 2026-07-17, extraction still pending) | None if direct sklearn metrics are adopted |
| `src/archive/utils/plots.py` (already archived 2026-07-17, extraction still pending) | Desired visual conventions |
| `notebooks/diagnostics/solver_comparison.ipynb` (moved 2026-07-17, was `_diagnostic_solver_comparison.ipynb`, originally `16b_optimizer_solver_comparison.ipynb`) | Solver acceptance evidence, if adopted by Stage 16 |

## Keep as reference, not canonical

- `notebooks/production/14_cit_model_feature_matrix.ipynb` Parts 2-3 (merged 2026-07-19 from the former `15_cit_model_benchmark.ipynb` + `16_cit_shap_importance.ipynb`)
- `notebooks/production/17_tam_constraint_analysis.ipynb`
- `notebooks/diagnostics/solver_comparison.ipynb` (moved 2026-07-17, was `_diagnostic_solver_comparison.ipynb`)
- `pipeline/solver_comparison.py`
- Existing generated figures and model artifacts

Reason: useful experimental or diagnostic evidence, but results cannot be treated as valid without reproducible generation manifests.

## Archive readiness criteria

A file becomes safe to archive only when:

1. Every reusable function is mapped to a tested target `src/` module or explicitly rejected.
2. Every diagnostic plot is reproduced or intentionally dropped.
3. No active import, subprocess call, dashboard fetch, or documented operating procedure uses it.
4. Target Stage 16 confirms approved output equivalence or documents an approved methodology change.
5. Engineering-review conflicts affecting the file are resolved.
6. The archive action is separately approved.

