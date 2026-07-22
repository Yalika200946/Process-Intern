Status: PROPOSED (reconciliation pass, 2026-07-22)

# Migration plan

No code changes are included in this pass, per the review's scope boundary. This is the proposed order for a follow-up implementation phase.

## Phase 0 - Freeze and label (no logic changes)
1. Add a generation_id + approval_status banner to the current dashboard as-is (L01). This alone converts every existing screen from "looks final" to "visibly provisional," which is the single highest-leverage, lowest-risk change available.
2. Add the missing per-row F=1/area-unverified caveat to every U_relative chart and the furnace THB banner (L06/L08/L22) without changing any number - just labelling.
3. Do not regenerate dashboard/data yet. This phase is purely trust-and-label.

## Phase 1 - Regenerate Level A/B content from the canonical pipeline
4. Point Data Quality and HX Performance (apparent Qcold/LMTD/UA only) at the current Codex Stage 04/07 outputs.
5. Retire the dashboard's independent `U_relative` computation path in favor of canonical apparent-UA + the 4-HX empirical reference (L08/L12), with the reduced 4-HX scope visually enforced.
6. Resolve the E112C tag mismatch identified in an earlier review of `src/features/heat_duty.py` before trusting any regenerated Qcold series for that HX.

## Phase 2 - Gate Level C and D explicitly
7. Reframe the cleaning-plan wizard, furnace-cost banner, forecast threshold, and both rankings behind the Level D "requires" checklist (see `product_information_architecture.md`). Nothing here needs new engineering work yet - only re-labelling existing content as EXPLORATORY/BLOCKED per the reconciliation CSV's severity=CRITICAL rows (L06, L11-L25 mostly).
8. Converge the two ranking systems (L24) into one, even if both remain EXPLORATORY, so there is only one number to eventually validate.
9. Consolidate the two independent network-modelling efforts (CLI-005) into one canonical track; archive the superseded one with a MIGRATION_MAP entry.

## Phase 3 - Close missing requirements (see missing_requirement_list.md), unblocking Level D incrementally
10. Each of the 10 missing requirements maps to specific formula_registry.csv rows currently BLOCKED_BY_DATA or NOT_IMPLEMENTED. As each requirement clears engineering sign-off, flip only the dashboard sections that depend on it from BLOCKED to PROVISIONAL/VALIDATED - do not wait for all 10 before unblocking any of them.
11. Re-run this reconciliation (or a scoped subset of it) after each requirement closes, since closing one (e.g. approved area/F) changes the numerical_match/status_match columns for several logic_ids at once (L06 through L14 all depend on area/F).

## Explicit non-goals for this migration
- Do not invent new engineering formulas to fill gaps (per the task's boundary and REVIEW_GUIDE.md's prohibited-claims list).
- Do not let the dashboard regain its own competing implementation of any canonical formula; every calculation should be read from an approved pipeline artifact.
- Do not collapse Level C back into Level B/D once separated - the exploratory/permanent-non-action distinction is load-bearing for the prohibited-claims list.
