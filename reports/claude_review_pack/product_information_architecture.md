Status: PROPOSED (reconciliation pass, 2026-07-22)

# Proposed information architecture

Mirrors `dashboard_readiness.csv`'s four levels directly, rather than the current five task-oriented tabs (ภาพรวม/แผนล้าง/พยากรณ์/เตา/หลักฐาน) which mix validated, provisional, exploratory, and blocked content within the same tab.

```
Level A - Data Quality (VALIDATED)
  - availability / missingness / flatline heatmaps
  - operating-state timeline
  - valid-record coverage per HX

Level B - HX Performance (PROVISIONAL, F/area caveat always visible)
  - Qcold, LMTD, apparent UA per HX (labelled apparent, F=1)
  - existing furnace live-snapshot panel (KEEP_AS_IS content)
  - existing 13-constraint table (KEEP_AS_IS content)

Level C - Experimental Analytics (EXPLORATORY, permanent non-action banner)
  - empirical reference / relative performance (scoped to the 4 reference HX only)
  - HX-CIT screening (with the E113A leakage caveat attached)
  - pilot network mix/propagation (E103AB->E104 branch only)
  - furnace physics-duty estimate (no THB conversion)
  - forecast benchmarks (with explicit "did not beat persistence" flags, no threshold-crossing claims)

Level D - Cleaning Decision (BLOCKED until prerequisites clear)
  - today's cleaning-plan wizard, ranking, and economics content moves here
  - rendered but visually locked/greyed with a clear "requires: confirmed condition + network consequence + economics + maintenance evidence" checklist showing which prerequisites are met
  - once individually unblocked, sections unlock incrementally rather than all-or-nothing

Cross-cutting (visible from every level)
  - generation_id + approval_status banner (per L01)
  - Evidence & Confidence tab, extended per ux_opportunities.md item 2, reachable from anywhere
```

## Why this shape

The current IA groups by *user task* (plan a clean, check the furnace, see evidence), which is a reasonable end-state but currently hides exactly how provisional most of the underlying numbers are, because a "task" tab freely mixes Level A/B/C/D content. Grouping by *evidence maturity* first makes the BLOCK_UNTIL_VALIDATED classification from the component CSV structurally impossible to miss, and gives the migration plan a natural incremental order: ship Level A and B first (both mostly ready), keep C clearly exploratory, and gate D behind the missing-requirements checklist until it closes.
