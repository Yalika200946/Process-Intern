# Phased Migration Plan

**Status:** CURRENT

## Purpose

`TARGET_PIPELINE.md` and the rest of the Codex analysis define the target
*shape* of the pipeline (16 single-question notebooks, medallion data
layers, full manifest/approval-gate governance). That target is correct as
a north star, but adopting it in one step is out of proportion to this
project's current size (one analyst, no formal multi-role sign-off
process yet). This plan sequences adoption so that:

- the specific pain the user reported (notebook ordering is confusing and
  hard to review) gets fixed early and cheaply;
- the correctness bugs the audit found get fixed before more work is
  built on top of them;
- the governance machinery (run manifests, hash lineage, 13 approval
  gates) is deferred until the project actually needs it.

Nothing in this plan authorizes moving, renaming, or deleting a legacy
file. Each phase below still requires separate explicit approval per
`CLAUDE.md` before any archive/rename action is executed.

## Phase 0 — Fix known correctness bugs (do first, before any reorg)

Source: `docs/Q_NORM_AUDIT.md`. These are active defects in code used by
the current production chain, independent of any restructuring decision.

1. `notebooks/cpht_features.py::compute_q_features`, cold-side branch
   (line ~211): missing `*(Tout - Tin)` term. `Q` is not heat duty; every
   `_Q_norm` feature built from it feeds the CIT models
   (10/11/12, `gen_honest_metrics.py`) and is wrong. Add the missing term
   to match the hot-side branch two lines below it, then retrain/re-run
   10–12 and diff the metrics against the current (buggy) baseline.
2. Reconcile `notebooks/cpht_config.py` vs `notebooks/cpht_features.py`
   E112C tag definitions — they currently disagree, so the fouling
   pipeline and the CIT-model pipeline see E112C as two different
   physical signals. Needs an engineering decision (spare shell vs
   separate upstream position, per `UNRESOLVED_ENGINEERING_DECISIONS.md`
   §2.1) before it can be fixed in code, not just a code fix.
3. Add an explicit low/near-zero total-charge denominator guard directly
   in the Stage-04 `Q_norm` calculation. Today it only relies on upstream
   shutdown removal; notebook 09's duplicate formula already guards
   against exact zero but nothing else does.
4. Reconcile the three coexisting `Q_norm` formulas (Stage 04
   variable-property, notebook 09 fixed-property, `cpht_features.py`
   missing-dT) into one, or explicitly retire the non-canonical ones.
   Blocked on the same engineering approval as item 2 for the
   *interpretation*, but the missing-dT bug (item 1) is not blocked —
   fix that regardless of which formula is eventually approved.

Do not label any Q_norm-derived output as a fouling indicator until this
phase is closed — `CLAUDE.md` already requires this.

## Phase 1 — Reorder and consolidate existing notebooks (the stated pain point)

Goal: apply the clean 00–16 naming/sequence from `TARGET_PIPELINE.md`
directly to the *existing* logic, without building bronze/silver/gold
layers or the manifest system yet. This is the smallest change that
fixes "sequence is confusing, hard to review."

1. Map each current notebook to its target slot using
   `PROPOSED_CLEAN_DEPENDENCY_GRAPH.md` (already drawn) — e.g. NB04 →
   target 07/09, NB08 → target 13, NB12 → target 08/11/14.
2. For each notebook, add the short header block from
   `TARGET_NOTEBOOK_CONTENT_PLAN.md` (question, inputs, outputs,
   upstream/downstream stage) — this alone removes most of the
   "have to open every notebook to know what feeds what" problem, at
   near-zero engineering risk.
3. Resolve the overwrite chains flagged in `CURRENT_PIPELINE_MAP.md`
   ("Overwrites and duplicate outputs" table) by picking one writer per
   file:
   - `Fouling_Rate_By_Run.csv` / `Feature_calculated.csv`: notebook 02
     stops writing preliminary versions; `compute_fouling_rate.py` becomes
     the sole writer, called explicitly from the notebook that needs it
     rather than silently re-run later.
   - `model_metrics.json`, `forecast_6mo.json`: fold `gen_honest_metrics.py`
     / `add_forecast_intervals.py` into notebook 13's own export cell so
     there is one writer, not a notebook followed by a silent mutator.
4. Delete the duplicate Q_norm/CIT-feature logic in
   `09_cit_model_feature_matrix.ipynb` once Phase 0 item 1 lands in
   `cpht_features.py` — the notebook should call the shared function, not
   reimplement it with different (and now provably wrong) fallbacks.
5. Archive candidates from `ARCHIVE_CANDIDATES.md` "already archived or
   scratch" and "orphan" lists — subject to your explicit sign-off per
   file, not a bulk move.

No new folder layers, no Parquet migration, no manifest system in this
phase. Same file formats, same `outputs/`/`dashboard/data/` locations —
just fewer notebooks, clearer sequence, no silent overwrites.

## Phase 2 — Wire up the config/contract system that already exists

`config/data_contracts.yaml`, `src/schemas.py`, and
`tests/test_data_contracts.py` already implement stage-contract
validation for stages 00–16, and `config/tag_mapping.yaml`,
`config/operating_limits.yaml`, `config/hx_configuration.yaml`,
`config/data_quality_rules.yaml` already exist as real config files, not
just planned ones. This phase is cheap because it extends work already
committed, not new scaffolding.

1. For each notebook touched in Phase 1, validate its output against the
   matching contract in `data_contracts.yaml` using `src/schemas.py`
   before declaring the notebook done.
2. Continue the pattern from "Centralize scattered TAM/outlier thresholds
   into cpht_config.py" (already done for one area) — move any remaining
   hard-coded limits/thresholds in notebooks 04–14 into the existing YAML
   configs rather than introducing new config files.

## Phase 3 — Parquet + lineage columns (mandatory `CLAUDE.md` rules, not yet applied)

Apply incrementally, starting with the outputs touched by Phase 0's fix
(so the corrected Q_norm/fouling tables are the first ones done right):

1. Switch canonical processed outputs from CSV to Parquet, stage by
   stage, starting with `Feature_calculated.csv` /
   `Fouling_Rate_By_Run.csv`.
2. Add `MEASURED` / `CALCULATED` / `INFERRED` / `ASSUMED` lineage columns
   to those tables, per the existing `CLAUDE.md` rule and the
   `common_output_columns` block already defined in
   `data_contracts.yaml`.

## Phase 4 — Deferred: full governance layer

Explicitly out of scope until the project moves beyond internship
deliverable status: `data/raw|bronze|silver|gold` folder restructure,
run-manifest/hash system, and the 13 cross-stage approval gates in
`TARGET_PIPELINE.md` §5 (each naming a specific engineering role as
approver). Revisit only if the pipeline is formally handed off to a team
that can staff those approvals.

## Sequencing note

Phases 0 and 1 do not depend on any of the unresolved engineering
decisions in `UNRESOLVED_ENGINEERING_DECISIONS.md` except where explicitly
noted (E112C topology). They can start immediately. Phases 2–3 depend on
Phase 1's notebook consolidation being in place so there is one writer per
output to attach a contract to.
