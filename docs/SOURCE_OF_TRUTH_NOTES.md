# Source-of-Truth Notes

**Status:** CURRENT

*(Formerly `SOURCE_OF_TRUTH_CANDIDATES.md` — its "Candidate register" table duplicated `SOURCE_OF_TRUTH_REGISTER.csv` at a coarser grain and was dropped; the two sections below are the content that CSV doesn't cover, so they're kept as a companion note. See `SOURCE_OF_TRUTH_REGISTER.csv` for the per-calculation canonical-module/function/formula register.)*

## Explicit non-selections

The following are not selected as source of truth:

- Any post-TAM period as automatically clean.
- Any `Q_norm` formula as a fouling indicator.
- Either E112C topology definition.
- SHAP as causal HX-to-CIT impact.
- The XGBoost/RF/LSTM models as operational CIT forecasts.
- The fixed 8.05°C network CIT deficit.
- The assumed 9.0 t/h fuel-gas limit.
- Either plant or legacy economic formula.
- Any one of the current competing HX rankings.

All remain `REQUIRES_REVIEW`.

## Logic that can be migrated before engineering decisions

These are structural rather than methodological choices:

- Source checksums and run manifests.
- Parquet I/O and schema validation.
- Chronological split utilities and leakage audits.
- Generic unit conversion with explicit units.
- Plotting/report conventions.
- Measured/calculated/inferred/assumed lineage fields.
- Atomic Stage 15/16 publication.
- Dashboard serializers that contain no engineering formulas.
