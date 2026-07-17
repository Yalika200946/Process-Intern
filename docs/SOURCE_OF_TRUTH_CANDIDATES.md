# Source-of-Truth Candidates

## Status vocabulary

- **CANDIDATE:** strongest current implementation to preserve as evidence during migration.
- **REQUIRES_REVIEW:** no canonical implementation may be selected without engineering approval.
- **EXPERIMENTAL:** may be retained for comparison but cannot feed the approved pipeline.
- **SERIALIZER_ONLY:** logic should shape approved tables, not recalculate engineering values.

## Candidate register

| Domain | Best legacy evidence | Target owner | Status | Required decision |
|---|---|---|---|---|
| Project run context | `pipeline/run_all.py` logging/backups | 00 | CANDIDATE for requirements only | Replace mutable execution with immutable run manifest |
| Business constraints | Requirements docs plus scattered config/comments | 01 | REQUIRES_REVIEW | Confirm owners, limits, units and acceptance tests |
| Tag mapping/topology | `cpht_config.py`, `cpht_features.py`, bypass workbook | 02 | REQUIRES_REVIEW | Resolve E112C and all shared/inferred instrumentation |
| Raw ingestion | NB01 parsing and backend validators | 03 | CANDIDATE | Preserve parsers, not cleaning or overwrite behavior |
| Data-quality rules | NB01 plus `nb_audit.data_quality_report` | 04 | REQUIRES_REVIEW | Approve ranges, shutdown and non-future imputation rules |
| Operating modes | NB03 plus `bypass_config.py` | 05 | REQUIRES_REVIEW | Approve E101G and shell-switch inference |
| Crude properties | `crude_properties.py` | 06 | REQUIRES_REVIEW | Approve correlations and reject/retain fixed-property fallbacks |
| Heat duty | `cpht_features.compute_q_features` plus NB02 checks | 07 | REQUIRES_REVIEW | Resolve tags, fixed/variable properties and approved Q_norm |
| LMTD/UA | No complete consistent implementation | 07 | REQUIRES_REVIEW | Define where true LMTD/UA is possible versus proxy-only |
| Clean HX baseline | State-aware baseline in `compute_fouling_rate.py`; predictive Q baseline in NB06 | 08 | REQUIRES_REVIEW | Define clean-reference acceptance and whether two baseline types are needed |
| Fouling rate | `nb_audit.robust_fouling_rate` | 09 | REQUIRES_REVIEW | Approve thresholds, curve set and current-rate definition |
| Cleaning events | NB02 event signals plus `export_cleaning_history.py` evidence/confidence | 10 | REQUIRES_REVIEW | Confirm event register and maintenance-log precedence |
| CIT impact | NB05, NB12 and event-study evidence | 11 | REQUIRES_REVIEW | Select estimands; do not equate correlation, SHAP and counterfactual gain |
| Furnace current headroom | `build_dashboard_topology.py` plus alert tests | 11 | REQUIRES_REVIEW | Confirm all limits and directions; move calculation out of dashboard |
| CIT forecasting | Persistence benchmark in `gen_honest_metrics.py` | 12 | CANDIDATE baseline | No ML deployment until it beats baseline for a declared horizon |
| Fouling forecasting | NB06/PHM/EOR candidates | 12 | REQUIRES_REVIEW | Select target, horizons, uncertainty and fallback |
| Cleaning priority | NB08 risk components | 13 | REQUIRES_REVIEW | Agree one score decomposition and one schedule |
| Network scheduling | `cleaning_scheduler_network.py` plus `solver_comparison.py` | 13 | REQUIRES_REVIEW | Approve reduced-form network, constraints and solver acceptance |
| Economics | `export_economics.py` evidence/calibration structure | 14 | REQUIRES_REVIEW | Approve formula, prices, costs, additivity discount and uncertainty |
| Dashboard serialization | `export_hx_timeseries.py`, `export_engineering_priority.py` | 15 | SERIALIZER_ONLY | Replace ad hoc JSON with approved schemas |
| Validation | Existing tests plus NB15/evidence concepts | 16 | CANDIDATE for checks | Rebuild around run manifests, schemas and fail-closed publication |

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

