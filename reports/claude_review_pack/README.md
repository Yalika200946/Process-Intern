# Claude Independent Review Pack — CPHT–F101

Snapshot date: 2026-07-22  
Purpose: independent engineering-logic review and dashboard redesign input.

## Non-negotiable boundary

- Canonical engineering calculations belong to the Codex pipeline and the source functions named in `registries/formula_registry.csv`.
- Claude must not create competing formulas in browser JavaScript, UI components, notebooks, or a parallel dashboard pipeline.
- Any discrepancy between source code, registry, output, unit, topology, or dashboard must be reported before implementation.
- UI redesign may begin only after logical reconciliation. A redesign must preserve status, provenance, warning, approval, generation, and blocker semantics.
- This pack is review evidence, not proof that every capability is plant validated.

No secrets, credentials, raw plant datasets, or unnecessary full time-series datasets are included. Representative outputs are aggregate or limited review artifacts.

## Recommended review order

1. Read this file and `REVIEW_GUIDE.md`.
2. Review topology, unit, property, and area/F registries.
3. Trace each applicable formula from `formula_registry.csv` to its source function and tests.
4. Review reference/clean semantics and cleaning-event evidence before interpreting condition results.
5. Review model registry and leaderboard; code existence is not validation.
6. Review network gates before any CIT or counterfactual claim.
7. Review furnace, forecast, decision, and optimization prerequisites.
8. Reconcile dashboard contracts and screenshots against the registries and representative outputs.
9. Produce a discrepancy register before changing the dashboard.

## Pack contents

- `REVIEW_GUIDE.md`: project questions, architecture, semantics, equations, gates, limitations, and prohibited claims.
- `registries/`: canonical formula/model/configuration snapshots and coverage/status registers.
- `evidence/`: test, model, engineering-sense, and dashboard verification evidence.
- `outputs/`: small representative outputs; these are not raw source data.
- `screenshots/`: selected current dashboard views for UI review.
- `SOURCE_MANIFEST.csv`: provenance and intended use for every copied artifact.

## Interpretation rule

Use status fields literally. In particular, `PROVISIONAL`, `EXPLORATORY`, `BENCHMARK_ONLY`, `ASSUMPTION`, `BLOCKED`, and `NOT_IMPLEMENTED` must not be visually or verbally promoted to validated plant conclusions.

