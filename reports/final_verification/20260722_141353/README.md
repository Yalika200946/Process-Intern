# Independent CPHT-F101 verification package

## Verdict

The canonical pipeline regenerates successfully and tests pass, but the project is an **engineering analytical prototype**, not a plant cleaning-decision system. Data quality, Qcold and LMTD are the strongest outputs. Apparent UA is provisional because F/area are not approved. Confirmed clean state, confirmed fouling, full network CIT recovery, attributable furnace saving, cleaning optimization and economics remain blocked.

## Checkpoint

- Branch: `fast-track/end-to-end-20260722`
- Commit: `f3298486474562a85b97070836ad83475b3fdeda`
- Tag: `verification/full-review-20260722-141353`
- Canonical run: exit 0 in 833.7 seconds
- Tests: 232 passed, 1 skipped, 14 warnings

## Inventory

- Relevant artifacts inventoried: 683
- CSV tables reviewed: 156
- Figures opened/programmatically checked and placed in contact sheets: 281
- Formula rows reviewed: 39
- HX review rows: 17
- Model leaderboard rows: 24
- Engineering issues: 8

## Major findings

1. A legacy performance table labels example-area-derived `U` as validated; use corrected apparent-UA output instead.
2. Pilot configuration gates and the full-network hard gate use conflicting readiness wording; full network remains blocked.
3. E104 counterfactual is an outlet-temperature experiment, not CIT recovery.
4. All 125/96 signal event results are exploratory; zero cleaning events are confirmed.
5. Forecasts have no approved threshold and three of four linear trends lose to persistence.
6. Decision/economics/optimization outputs must not be used for plant action.

## Package links

- [Artifact inventory](artifact_inventory.csv)
- [Table review](table_review_register.csv)
- [Figure review](figure_review_register.csv)
- [Figure gallery](gallery/index.html)
- [Equation verification](equation_unit_verification.csv)
- [HX review](hx_complete_review.csv)
- [HX cards](hx_cards/)
- [Model verification](model_verification_register.csv)
- [Sense checks](engineering_sense_check_register.csv)
- [Cross-file reconciliation](cross_file_reconciliation.csv)
- [Dashboard verification](dashboard_verification_report.md)
- [Presentation selection](presentation_artifact_selection.csv)
- [Completeness metrics](completeness_metrics.csv)
- [100-point scorecard](engineering_scorecard_100.csv)
- [Correction plan](correction_plan.csv)
- [Reproducibility comparison](reproducibility_comparison.csv)
- [Canonical log](canonical_pipeline.log)
