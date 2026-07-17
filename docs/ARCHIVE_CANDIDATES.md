# Archive Candidates

No file should be moved or deleted until the target pipeline reproduces approved outputs and the user gives separate approval.

## High-confidence archive candidates

### Already archived or scratch

- All files under `notebooks/_archive_2026-07-12/`.
- `notebooks/_archive_2026-07-12/scratch_fouling/`.

Reason: no active production callers; superseded or prototype logic; stale configurations.

### Notebook builders

- `notebooks/_build_cleaning_plan_notebook.py`
- `notebooks/_build_solver_comparison_notebook.py`

Reason: duplicate editable sources for generated notebooks. Preserve temporarily for provenance only.

### Legacy generic ML framework

- `src/core.py`
- `src/core_stateless.py`
- `src/core_configs.py`
- `src/utils/configs.py`
- `src/utils/modelFuncs.py`
- `src/utils/models.py`
- `src/utils/prints.py`
- `src/utils/utilities.py`

Reason: no active CPHT downstream users; hidden/global conventions; old model persistence; incomplete dependencies; target pipeline will use domain-specific modules.

### Superseded user interfaces and schedulers

- `dashboard/dashboard_pro.html`
- `pipeline/cleaning_scheduler.py`

Reason: superseded UI and competing independent scheduler. Keep scheduler temporarily as a simple baseline until Stage 13 validation is approved.

## Conditional archive candidates after logic extraction

| File | Required extraction first |
|---|---|
| `_eda_process_control.ipynb` (renamed from `00_data_prep_process_control.ipynb`, Phase 1) | Inventory/DQ representative plots |
| `_eda_correlation_and_pca.ipynb` (renamed from `02b_correlation_and_pca.ipynb`) | Selected exploratory diagnostics |
| `09_cit_model_feature_matrix.ipynb` | Any useful plotting/reference only; calculations should be rebuilt |
| `phm_config.py` | Approved horizon/scenario settings |
| `src/utils/analysis.py` | Any desired PCA/report plotting patterns |
| `src/utils/metrics.py` | None if direct sklearn metrics are adopted |
| `src/utils/plots.py` | Desired visual conventions |
| `_diagnostic_solver_comparison.ipynb` (renamed from `16b_optimizer_solver_comparison.ipynb`) | Solver acceptance evidence, if adopted by Stage 16 |

## Keep as reference, not canonical

- `10_cit_model_benchmark.ipynb`
- `11_cit_shap_importance.ipynb`
- `14_tam_constraint_analysis.ipynb`
- `_diagnostic_solver_comparison.ipynb`
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

