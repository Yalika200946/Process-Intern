Status: CURRENT (capability audit, 2026-07-22). No source code was modified to produce this report.

# CPHT-F101 Existing-System (Claude) Capability and Engineering Audit

Scope boundary used throughout (verified via `git log --diff-filter=A`, not assumed): everything up to and including commit `9230d07` ("snapshot full system and define MVP boundary", 2026-07-21) is "the Claude implementation." Everything dated 2026-07-22 onward is "Codex," already covered by the separate reconciliation pass earlier this session (`reports/claude_review_pack/`).

Full inventories: [claude_existing_capability_inventory.csv](claude_existing_capability_inventory.csv) (32 capabilities) · [claude_formula_registry.csv](claude_formula_registry.csv) (35 formulas) · [claude_model_registry.csv](claude_model_registry.csv) (17 models) · [claude_workflow_and_dashboard_map.md](claude_workflow_and_dashboard_map.md) · [claude_codex_capability_comparison.csv](claude_codex_capability_comparison.csv) (15 rows) · [smartpm_capability_gap_matrix.csv](smartpm_capability_gap_matrix.csv) (16 rows).

## A. Existing valid Claude work to preserve

- The **v2 SLSQP network cleaning scheduler** (`pipeline/cleaning_scheduler_network.py`, C16/CF19) — a real, paper-adapted, live-tested optimizer with no bugs found in its objective/constraint math on manual review this session. Codex has no equivalent at all (`optimization_readiness.csv` marks scheduling BLOCKED).
- The **CIT walk-forward model-honesty pipeline** (`pipeline/gen_honest_metrics.py`, C11/CM08) — persistence correctly beats ML on every fold, with an ablation proving *why*. This is a stronger validation design than Codex's single chronological 80/20 split for the analogous HX-CIT task.
- The **robust fouling-rate estimator** (`src/validation/nb_audit.py`, C07/CF09) — Theil-Sen + AIC curve race + a reliability gate that correctly excludes 49/97 noisy runs rather than overclaiming. Executed on real data; Codex's equivalent formula has never run at all.
- The **PHM suite** (RUL Monte-Carlo, Weibull survival, degradation backtest, SHAP drivers) — a unique capability with no Codex counterpart, all executed on real data, with appropriate self-gating (the SHAP driver panel is currently hidden because it doesn't beat its own baseline).
- The **entire interactive dashboard** — the only UI in the repository; Codex's output is static figure galleries and CSV registries.
- **Measured-first economics** (`pipeline/export_economics.py`, C13) with a self-check against a known reference number.

## B. Claude calculations that require Codex-style validation

- **Furnace fuel/CO2 constants (LHV, efficiency)** — hardcoded rather than config-loaded, same missing-approval status as Codex's equivalent formula (F34). Wrap in Codex's approval_status framework rather than re-deriving.
- **Economics formula (F35-equivalent)** — Claude's version is executed and self-checked, but neither side has an engineer-approved price/constant basis. Needs the same sign-off Codex is waiting on.
- **Empirical-reference scope** — Claude applies its per-run clean baseline to all 16 HX; Codex restricts an analogous concept to 4 HX with explicit confidence tiering. Worth an engineering review of whether Claude's per-run reliability gate (48/97) already compensates for the broader scope, or whether it should also narrow.
- **Hybrid network model** (`src/network/hybrid.py`) — already self-gated as not usable for cleaning-event prediction; needs reconciliation with Codex's separate, also-unvalidated pilot-network effort rather than two parallel unconfirmed attempts sitting side by side.

## C. Claude calculations that appear incorrect or semantically unsafe

- **E112C tag mapping bug** (`src/features/heat_duty.py`, confirmed earlier this session): a duplicate `HX_CONFIG` cross-wires E112C's outlet to E105AB's tag (`1TI114.pv`) instead of the correct shared E113A tags. This is a live, real bug affecting every downstream number for that HX (Q duty, fouling rate, ranking).
- **`Q_norm`'s silent dual formula** (same file) — the column means `Q/charge` when flow data exists and `dT/charge*100` when it doesn't, under one name, with no unit flag distinguishing the two.
- **Furnace-cost dashboard banner** shows a concrete THB/day figure with zero caveat in the UI, even though the pipeline code that feeds it explicitly labels the same calculation diagnostic-only/small-n. The unsafe part is the UI, not the formula.
- **Weibull shape-parameter discrepancy** — live `reliability.json` reports pooled shape=0.689 (decreasing hazard); prior project memory notes a shape≈1.26 (wear-out, increasing hazard) figure. These describe opposite physical behaviors. **This is flagged, not resolved** — it needs a human check against the actual fit history before either number is trusted operationally.
- **Two disagreeing rankings** (`engineering_priority_score` vs `hx_ranking.json`'s `priority_score`) feed different dashboard tabs with no arbitration rule, despite the codebase's own stated intent to have one primary ranking.

## D. Codex improvements to incorporate

- **Approval-status/confidence field discipline** — every Codex output row carries status, confidence, source, and limitation; almost no Claude `dashboard/data/*.json` artifact does. This is the single highest-leverage governance improvement available and requires no formula changes.
- **Statistical change-point detection** (CUSUM/EWMA/robust-median-step) for cleaning-event candidates, as an addition alongside Claude's existing rule/config-based taxonomy, not a replacement.
- **Narrower, explicitly-scoped empirical reference** (4 HX with stated confidence tier) as a model for how to present Claude's broader 16-HX baseline more honestly, if engineering review decides the broader scope isn't independently justified.
- **`src/schemas.py` should actually be wired into `pipeline/run_all.py`** — this is Claude's own code, already built, simply never called. Codex's practice (using its registries as an active governance layer) is the model to follow; the mechanism to use is Claude's own.

## E. Existing Claude functions that are more complete than the Codex proposal

- Fouling-rate estimation (executed vs never-executed on Codex's side).
- CIT forecasting validation methodology (walk-forward CV vs single split).
- Economics engine (executed + self-checked vs never-executed).
- Cleaning-schedule optimization (a full working optimizer vs entirely BLOCKED).
- PHM (RUL/Weibull/degradation/drivers) — no Codex equivalent exists.
- The dashboard itself — no Codex equivalent exists.

## F. UX/UI improvements needed for a professional engineering product

1. Add per-widget approval-status/confidence chips (adopting D's governance pattern) instead of the single global "ENGINEERING REVIEW MODE" banner — this was already identified in the earlier Codex reconciliation and applies equally here.
2. Fix the CIT-simulation chart's out-of-order x-axis date labels (cosmetic bug, already flagged this session).
3. Fix the multi-variable overlay chart's shared-axis scale problem (U_relative disappears next to Q duty in kW) — add a secondary axis.
4. Reconcile or visually distinguish the two disagreeing rankings (C24) rather than letting a user land on either one unknowingly.
5. Surface the hybrid network model and network-diagnostics outputs (C17/C18) somewhere in the UI even in a clearly EXPLORATORY/self-gated-failed state, rather than leaving genuinely interesting (if unvalidated) work completely invisible.
6. Add an Engineer/Operator mode distinction (SmartPM gap, currently MISSING).

## G. New data or engineering evidence required

1. Approved HX transferable area, active-shell basis, and LMTD correction factor — blocks a verified U on both Claude's and Codex's side identically.
2. Confirmed maintenance/cleaning history — would let `CONFIRMED_CLEAN` actually fire in Claude's existing (already-correct) taxonomy instead of never firing.
3. Approved furnace LHV/efficiency constants — needed to make both the pipeline formula and the dashboard banner honest.
4. A resolved Weibull shape-parameter question (C above) — needs someone to check the fit history/inputs, not new plant data necessarily.
5. Source-pipeline identification for `hx_ranking.json` (C24) — needed before it can be reconciled with or retired in favor of `engineering_priority_score`.

---

# Unified target architecture

```
                    +-----------------------------------------------------+
                    |  ONE production pipeline (Claude's existing modules  |
                    |  as the computational core; Codex's registry/status |
                    |  framework as the governance wrapper)                |
                    +-----------------------------------------------------+
Raw data -> validation -> properties -> HX calc (single HX_CONFIG source -
    fix the E112C duplication, do not create a third copy)
  -> per-run clean baseline -> fouling curve/rate (Claude's Theil-Sen+AIC,
     already the stronger implementation)
  -> cleaning events (Claude's rule-based taxonomy AS THE PRIMARY signal,
     Codex's CUSUM/EWMA as an ADDITIONAL candidate source, both feeding
     one event registry with one confidence scheme)
  -> ranking (converge engineering_priority_score and hx_ranking.json into
     ONE score; retire whichever does not survive source-tracing)
  -> network (consolidate hybrid.py and Codex's pilot-network effort into
     ONE validation track with ONE acceptance bar)
  -> furnace/economics (Claude's executed formulas, Codex's approval-status
     fields, one set of engineer-approved constants replacing both sides'
     hardcoded ones)
  -> forecast/PHM (Claude's suite, unique, preserved as-is)
  -> optimization (Claude's v1/v2 schedulers, preserved as-is, output
     wrapped in approval-status so its EXPLORATORY/BLOCKED state is visible)
  -> src/schemas.py contract validation (Claude's own code, finally called
     from run_all.py)
  -> dashboard (Claude's existing UI, every artifact now carrying
     generation_id + approval_status + confidence + source + limitation)
```

Principles: no duplicated formulas (fix, don't triplicate, the HX_CONFIG problem), one ranking, one network-validation track, Codex's governance fields applied to Claude's existing computational modules rather than either side rewriting the other's math, and the dashboard remains the single UI reading only from versioned, status-carrying pipeline output.

---

# Prioritized implementation batch

| Priority | Item | Effort | Depends on |
|---|---|---|---|
| P0 | Fix E112C tag mapping in `src/features/heat_duty.py` (point at `src/domain/config.py`) | Small | None |
| P0 | Add approval-status/confidence fields to `dashboard/data/*.json` generation + a visible per-widget chip | Medium | None |
| P1 | Resolve the Weibull shape 0.689-vs-1.26 discrepancy (human check of fit inputs/history) | Small (investigation) | None |
| P1 | Trace `hx_ranking.json`'s source pipeline; converge the two rankings into one | Medium | None |
| P1 | Wire `src/schemas.py` into `pipeline/run_all.py` | Medium | None |
| P2 | Fix CIT-simulation x-axis labels and multi-variable chart axis scale | Small | None |
| P2 | Add explicit unapproved-constant caveat to the furnace-cost dashboard banner | Small | None |
| P2 | Consolidate `src/network/hybrid.py` with Codex's pilot-network effort into one validation track | Large | Engineering review of acceptance criteria |
| P3 | Add CUSUM/EWMA change-point detection alongside Claude's existing event taxonomy | Medium | None |
| P3 | Engineer review of empirical-reference scope (16 HX vs Codex's 4) | Medium | Engineering input |
| P3 | Add Engineer/Operator dashboard modes | Large | P0 (status framework) |

---

## CLAUDE CAPABILITIES ALREADY COMPLETE

Fouling curve fitting + robust rate estimation (48/97 reliable, executed on real data), CIT walk-forward forecasting honesty pipeline, measured-first economics engine, v1/v2 cleaning-schedule optimizers (both live on the dashboard), PHM suite (RUL/Weibull/degradation/SHAP drivers), the full interactive dashboard (5 tabs, live-tested), evidence/confidence disclosure patterns already in the Evidence tab and the 13-constraint table.

## CLAUDE CAPABILITIES PARTIALLY COMPLETE

Network-level CIT/counterfactual modelling (two internal attempts, both self-gated not usable), furnace fuel/economic impact (executed but on hardcoded, unapproved constants), cleaning-event detection (rule-based only, no statistical change-point detector), data-contract governance (built in `src/schemas.py`, never wired into the actual pipeline run), multi-scenario comparison (single scenario at a time in the wizard).

## VALID CLAUDE LOGIC TO PRESERVE

The v2 SLSQP network scheduler's objective/constraint formulation; the Theil-Sen+AIC+reliability-gate fouling-rate method; the walk-forward CV design for CIT forecasting; measured-first-with-calibrated-fallback economics; the PHM suite's self-gating behavior (SHAP drivers correctly hidden when they don't beat baseline); the compensation-ratio network diagnostic's refusal to sum local gains into a network total.

## CLAUDE LOGIC REQUIRING VALIDATION

Furnace LHV/efficiency constants; the 16-HX-wide empirical-reference scope; the hybrid network model's broader-but-failed counterfactual attempt; economics price/constant basis; `hx_ranking.json`'s unidentified source pipeline.

## CLAUDE LOGIC REQUIRING CORRECTION

The E112C tag-mapping bug in `src/features/heat_duty.py`; the silently dual-definition `Q_norm` column; the unasserted (print-only) economics slide self-check; the furnace-cost dashboard banner's missing caveat; the un-arbitrated dual-ranking system.

## CODEX IMPROVEMENTS TO INCORPORATE

Approval-status/confidence/source/limitation field discipline on every output; statistical change-point detection (CUSUM/EWMA) as an additional cleaning-event signal; the narrower, explicitly-tiered empirical-reference presentation pattern; the practice (not just the code) of actively enforcing contract validation in the pipeline run.

## CLAUDE FEATURES MORE ADVANCED THAN CODEX

The entire interactive dashboard (Codex has none); the v1/v2 cleaning-schedule optimizers (Codex's equivalent is entirely BLOCKED); the PHM suite (no Codex equivalent); the CIT-forecast walk-forward validation methodology (stronger than Codex's single-split HX-CIT screen); the executed-and-self-checked economics engine (Codex's has never run).

## SMARTPM-INSPIRED CAPABILITY GAPS

Engineer/Operator mode differentiation (MISSING); an interactive network canvas beyond the static P&ID (PARTIALLY_IMPLEMENTED); multi-scenario side-by-side comparison (PARTIALLY_IMPLEMENTED); validated network-wide consequence (IMPLEMENTED_NOT_VALIDATED on both internal Claude attempts); full thermodynamic-consistency enforcement rather than a diagnostic-only energy-balance check (PARTIALLY_IMPLEMENTED). No claim of equivalence to SmartPM's proprietary capability is made anywhere in this audit.

## UNIFIED TARGET ARCHITECTURE

One production pipeline: Claude's existing computational modules (formulas, models, optimizers, PHM, dashboard) as the core, with the E112C bug fixed and the dual-ranking/dual-network-effort duplications consolidated, wrapped in Codex's approval-status/confidence/source/limitation governance framework applied uniformly to every `dashboard/data/*.json` artifact, with `src/schemas.py` actually enforced in `pipeline/run_all.py`. No second, competing analytical pipeline. Full diagram above.

## NEXT IMPLEMENTATION BATCH

P0: fix E112C tag bug; add approval-status fields to dashboard data + UI chips. P1: resolve the Weibull shape discrepancy; trace and converge the two rankings; wire up `src/schemas.py`. P2: fix the two known dashboard chart bugs; add the furnace-banner caveat; begin consolidating the two network-modelling efforts. P3: add CUSUM/EWMA detection; engineering review of empirical-reference scope; Engineer/Operator dashboard modes. Full table above.
