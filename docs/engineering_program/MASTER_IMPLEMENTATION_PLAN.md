# CPHT-F101 Full Engineering Implementation Program

Status vocabulary is limited to `VALIDATED`, `IMPLEMENTED_NOT_VALIDATED`, `PROVISIONAL`, `EXPLORATORY`, `PARTIAL`, `BLOCKED`, `UNAVAILABLE`, `FAILED`, `INSUFFICIENT_DATA`, and `NOT_APPLICABLE`.

## Governing execution rule

The current fast-track pipeline and its accepted canonical cold-side calculations are preserved. Each batch must add only evidence-supported capability, run targeted tests, execute affected real-data stages, update registries and blockers, create a batch report, commit, and leave a clean worktree. A blocked prerequisite produces an explicit blocker artifact and cannot be bypassed with fabricated data.

## Batch sequence

1. Formula, unit, area, F-factor, and property completion.
2. HX performance and data-quality completion.
3. Reference, clean evidence, condition, and cycle analysis.
4. Baseline, condition, and HX-CIT model benchmarking.
5. Configuration-aware CPHT network validation.
6. Single-HX and eligible multi-HX counterfactual analysis.
7. Furnace physics, calibration, and consequence analysis.
8. Forecast model benchmarking.
9. Decision support and uncertainty.
10. Economics and optimization.
11. Dashboard and final integration.
12. Independent verification, scorecard, and final documentation.

## Hard gates

- Verified `U` requires verified area, verified F, and matching active-shell basis.
- Confirmed fouling requires confirmed clean-state evidence.
- Full-network CIT consequence requires configuration-specific flow and temperature closure through measured CIT.
- Fuel/economic consequence requires network-attributable CIT plus approved or explicitly scenario-labelled furnace/economic inputs.
- Final cleaning action requires condition, consequence, uncertainty, feasibility, economics, and operational constraints.

The machine-readable master gap matrix is `config/master_implementation_gap_matrix.csv`.

