# Archived legacy code

These modules are **not used** by any active CPHT notebook, `pipeline/`
script, or `backend/server.py` (confirmed via `rg` before archiving — see
`docs/ARCHIVE_CANDIDATES.md`). They are kept, not deleted, in case something
in them is worth reusing later.

- `core.py`, `core_stateless.py`, `core_configs.py` — an older, generic
  furnace-ML framework (hidden `ROOT_PATH`/`sys.path` conventions, TensorFlow
  model persistence) that predates the CPHT-specific pipeline. No CPHT
  downstream user. Replacement: none — current reusable logic lives in
  `src/domain`, `src/features`, `src/models`, `src/optimization`,
  `src/reporting`, `src/validation`.
- `utils/configs.py`, `utils/modelFuncs.py`, `utils/models.py`,
  `utils/prints.py`, `utils/utilities.py` — support code for the framework
  above (config loading, Keras/TF model builders, pretty-printing). Same
  status: no active importer.
- `utils/analysis.py`, `utils/metrics.py`, `utils/plots.py` — conditional
  archive candidates per `docs/ARCHIVE_CANDIDATES.md`: no active importer
  today, but flagged there as worth mining for reusable
  PCA/report/plotting conventions before a future cleanup deletes them.
  That extraction has not happened yet — treat this file as still holding
  that todo.

Do not import from `src/archive/` in new code. If you need something from
here, move the specific piece you need into its proper `src/` subpackage
first (with review), rather than importing the archived copy.
