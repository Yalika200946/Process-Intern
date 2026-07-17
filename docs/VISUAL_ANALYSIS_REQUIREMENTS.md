# Visual Analysis Requirements

**Status:** CURRENT

## Principles

- Notebooks show fleet summaries and representative cases, not all repeated HX plots.
- Full per-HX diagnostic sets are saved under `reports/figures/<stage>/per_hx/`.
- Every figure includes units, data period, run ID, and measured/calculated/inferred labels.
- A figure cannot turn association into causation through its title or annotation.
- Low-confidence and failed-quality examples must be shown alongside successful examples.

## Required visuals by target notebook

| Stage | Primary figures shown in notebook | Full saved outputs |
|---|---|---|
| 00 | None | Environment evidence is tabular |
| 01 | Optional requirement-coverage chart | None |
| 02 | CPHT topology; tag-coverage heatmap; lineage map | Asset/tag diagrams |
| 03 | Source coverage; overlap/gap timeline; sampling frequency | Per-source timelines |
| 04 | Missingness heatmap; critical-tag coverage; violation ranking; raw-vs-flagged overlay; gap distribution | Per-tag DQ overlays |
| 05 | Fleet mode timeline; service heatmap; E101 inference; E112C/E113A swap | Per-HX mode timelines |
| 06 | Crude-grade timeline; property trends; correlation matrix; correlation-domain checks | Per-grade/property diagnostics |
| 07 | Train duty profile; Q ranking/distribution; Q vs load; energy balance; representative histories | One standardized dashboard per HX |
| 08 | Clean-window overview; actual-vs-baseline; residuals; chronological validation; interval calibration | Per-HX baseline diagnostics |
| 09 | Fouling heatmap; rate ranking with intervals; linear fit; asymptotic fit; unreliable example | Per-HX/run fouling dashboards |
| 10 | Event timeline; aggregate event study; evidence/confidence matrix; switch example; TAM example | Per-HX event windows |
| 11 | CIT/fouling history; duty/fuel vs CIT; headroom chart; four-pass skin history; impact ranking; event response | Per-constraint and event diagnostics |
| 12 | Walk-forward validation; error vs horizon; interval calibration; HX forecast cone; CIT/headroom scenario | Per-HX forecast cones |
| 13 | Score decomposition; risk-effort matrix; Gantt; constraint utilization; optimizer-baseline comparison | Scenario schedules and solver diagnostics |
| 14 | Cost-benefit quadrant; payback; tornado plot; cumulative value; measured-vs-modeled gain | Per-scenario economics |
| 15 | Dataset completeness/freshness; payload size; schema status | Publication QA |
| 16 | Row-count waterfall; freshness timeline; model-baseline scorecard; physical violations; approval coverage | Full release evidence |

## Representative-case policy

Where applicable, each notebook should display:

1. One high-quality representative HX.
2. One high-risk/current-priority HX.
3. One special-topology HX, such as E101G or E112C/E113A.
4. One unreliable or data-limited case.

The representative set is selected by documented rules, not manually changed to make results look favorable.

## Standard per-HX figure packages

### Stage 07: performance

- Flow and inlet/outlet temperatures.
- Calculated Q and validity mask.
- Q versus charge/load.
- Optional hot/cold energy-balance comparison.

### Stage 08: clean baseline

- Candidate/approved clean windows.
- Actual and predicted clean performance.
- Residuals and prediction interval.
- Training/validation periods.

### Stage 09: fouling

- Performance ratio and Rf proxy.
- Run boundaries and phases.
- Selected curve and confidence interval.
- Reliability flags and excluded periods.

### Stage 10: events

- Mode and run timeline.
- Detected/confirmed events.
- Pre/post U, Q and CIT windows.
- Evidence and confidence annotation.

### Stage 12: forecast

- Current run history.
- Baseline and candidate forecasts.
- Prediction interval.
- Threshold crossing distribution.
- Assumptions/scenario label.

## Prohibited visual patterns

- Sixteen nearly identical plots embedded sequentially in a notebook.
- Truncated axes that exaggerate recovery or degradation without clear notation.
- SHAP plots titled as causal impact.
- `Q_norm` plots labeled “fouling” before approval.
- Post-TAM windows shaded “clean” without approval status.
- Forecast lines without uncertainty or baseline comparison.
- Rankings without component scores, missing-data flags, and feasibility status.
- Dashboard charts recomputing Q, CIT gain, fuel penalty, payback, or priority.

