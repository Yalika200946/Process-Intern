# Notebook Pipeline Redesign — `notebooks_v2/`

Status: **IN PROGRESS — Notebook 01 built, corrected, and verified against real data (data dictionary + config-import
fix as of 2026-07-16); 02-13 not yet built**

## Why this exists

The legacy pipeline (`notebooks/01_data_cleaning.ipynb` .. `16_cleaning_plan_optimization.ipynb`, 27 steps total via
`pipeline/run_all.py`) grew organically over many rounds of fixes (see `docs/ANALYSIS_PIPELINE_GUIDE.md`). It is
correct and validated, but its notebook boundaries don't map cleanly to a single analysis question each, several
notebooks exist mainly to feed other notebooks (`09_cit_ranking_baseline.ipynb` is really "build the feature matrix
for #10-12," not a standalone analysis), and there's no consistent documentation template — understanding *why* a
number changed requires reading code, not a structured Method/Results/Limitations section.

This redesign (`notebooks_v2/`) restructures the same underlying engineering logic into **13 notebooks, each
answering exactly one question**, each following the same 13-section template, so a reviewer can jump into any single
notebook and understand what it assumes, how it's validated, and what it hands off — without reading the other 12.

**The legacy `notebooks/` chain is untouched and keeps running** — `notebooks_v2/` is additive, not a replacement yet.
Both can coexist; `pipeline/run_all.py` still drives the dashboard from the legacy chain until `notebooks_v2/` is
fully built and verified.

## Structure

- `notebooks_v2/NN_Name.ipynb` — the 13 notebooks, each self-contained and runnable from VS Code / Jupyter.
- `src/cpht/` — reusable logic shared across `notebooks_v2/` (config, validation helpers, and — as later notebooks
  are built — Q-duty/fouling-rate/CIT functions). `src/cpht/config.py` **imports** `notebooks/cpht_config.py` and
  re-exports its constants (single source of truth) rather than duplicating them — an earlier draft hand-copied the
  constants instead, which repeated a failure pattern this project has already been burned by twice (see
  `notebooks/cpht_config.py` and `notebooks/bypass_config.py` header comments); corrected 2026-07-16, verified the
  fix changes nothing observable (`data_profile.json` byte-identical except timestamp before/after).
- `Data/v2/` — output artifacts from `notebooks_v2/`, kept separate from the legacy chain's `Data/*.csv` filenames so
  the two pipelines never overwrite each other's files while both exist.

## Standard notebook template (all 13 notebooks)

| Section | Purpose |
|---|---|
| Objective | What question this notebook answers |
| Inputs | Which files/tables it reads |
| Assumptions | What's assumed true going in |
| Requirements | Which requirement(s) from `docs/03` this notebook addresses (traceability) |
| Method | The approach/equations, in prose, before the code |
| Data Validation | Checks run on the input **before** any calculation (via `src.cpht.validation`) |
| Analysis | The actual computation |
| Results | What was found, restated in prose |
| Diagnostic Checks | Sanity checks on the *output* (plausibility, not just "did it run") |
| Limitations | What this result does NOT tell you |
| Outputs | Artifact(s) written for the next notebook |
| Conclusion | One-paragraph summary |
| Next Notebook | Explicit pointer to what comes next and why |

## Old → New mapping

| New notebook | Answers | Built from (legacy) | Status |
|---|---|---|---|
| 01 Requirements & Data Understanding | Is the raw file structurally sound? What's actually in it? | `notebooks/00_data_prep_process_control.ipynb` (EDA) + `docs/03` (requirements traceability) | ✅ **Built & verified** (2026-07-16, 97 tags, 2008 rows, 2021-01-01→2026-07-01, all required tags present). **Now also builds the docs/03 section 2.2/section 3 Data Dictionary in full** (17-field schema — Tag ID/Name/Description/Equipment/Process Side/Measurement Type/Unit/Sampling Frequency derived from real config+data; Valid/Warning/Critical bands and Owner left explicit `TBD` pending engineer sign-off, not fabricated), written to `Data/v2/data_dictionary.csv`. This was originally missing from the plan (docs/03 flags the Data Dictionary as the thing that should be built *first*) and is now closed. |
| 02 Data Ingestion & Tag Mapping | How do we get a clean, merged process+crude-assay table? | `notebooks/01_data_cleaning.ipynb` (ingestion half) + `00_data_prep_crude_assay.ipynb` | Not built |
| 03 Data Quality | Is the merged data trustworthy enough to compute on? | `notebooks/01_data_cleaning.ipynb` (outlier/chain-consistency half) + `notebooks/nb_audit.py`'s `data_quality_report` | Not built. **Must also build the combined per-HX Data Quality Score (docs/03 FR-DQ-012 — completeness × validity × consistency into one score)** — the legacy checks alone don't produce this; relocating them without adding the score would leave this requirement unmet, same as before the redesign. Should read `data_dictionary.csv` from Notebook 01 rather than re-deriving Equipment/Process Side/Criticality. |
| 04 Time Alignment & Operating Modes | Which HX/shell is actually running on any given day? | `notebooks/03_operating_state_classification.ipynb` | Not built |
| 05 Crude Property Calculation | What's Cp/density of the crude at each point in the train? | `notebooks/02_feature_engineering.ipynb` (Watson-Nelson/Rackett part) + `notebooks/crude_properties.py` | Not built |
| 06 HX Heat-Duty Calculation | How much heat is each HX actually transferring? | `notebooks/02_feature_engineering.ipynb` (Q calc) + `notebooks/cpht_features.py` | Not built |
| 07 Clean Baseline | What's "clean" performance look like, controlling for throughput/crude type? | `pipeline/compute_fouling_rate.py`'s initiation-phase baseline logic | Not built |
| 08 Fouling Analysis | How fast is each HX fouling, and how confident are we? | `pipeline/compute_fouling_rate.py` (robust Theil-Sen rate) + `notebooks/04_fouling_rate_estimation.ipynb` | Not built |
| 09 Cleaning Event Detection | When was each HX actually cleaned (inferred)? | **Currently scattered/implicit** across several legacy notebooks — no single explicit event table exists yet. This is a genuine gap, not just a restructure (docx `FR-CL-007/008`, confirm/reject UI, still doesn't exist either) | Not built — **needs real design work, not just extraction**. Confirmed via code read: `pipeline/export_cleaning_history.py` derives events *implicitly* every run by scanning `{hx}_event_type` columns for `SWITCH`/`TAM` reset rows (`days_on_duty==0`) — this heuristic is a usable **starting point to promote into an explicit, persisted event table with a confidence tag**, which is more buildable than a from-scratch design, though it still has no confirm/reject UI and no maintenance log to validate against. |
| 10 CIT & Furnace Impact | How does each HX's fouling translate to CIT loss and furnace constraint pressure? | `notebooks/05_fouling_cit_sensitivity.ipynb` + `pipeline/cleaning_scheduler_network.py`'s furnace-impact logic | Not built |
| 11 Forecasting | Where is CIT/fouling headed, and when does each HX hit its clean trigger? | `notebooks/06_fouling_rate_forecast.ipynb` + `07_time_to_clean_prediction.ipynb` + `13_cit_forecast_export.ipynb` | Not built |
| 12 Cleaning Prioritization | Which HX should be cleaned first? | `notebooks/08_cleaning_priority_ranking.ipynb` (incl. the 2026-07-16 safety-weight fix) + `16_cleaning_plan_optimization.ipynb` | Not built |
| 13 Dashboard Dataset & Final Report | Package everything for the dashboard + write the human-readable summary | All `pipeline/export_*.py` scripts, consolidated | Not built |

## Design notes carried over from the legacy pipeline (do not re-litigate)

These decisions were already made, validated, and documented in `notebooks/METHODOLOGY.md` and
`docs/02_Requirement_v2_SSOT.md` — `notebooks_v2/` reuses them as-is rather than re-deriving:
- Q duty is cold-side-only (hot-side data unreliable) — `docs/02` section 3.1
- Fouling rate uses robust Theil-Sen regression with physical-constraint checks (slope must be negative) —
  `pipeline/compute_fouling_rate.py`
- CIT prediction: persistence baseline beats ML on every walk-forward fold — ML kept for SHAP attribution only, not
  as the production forecaster — `docs/03` section 9
- Safety-weight in cleaning priority is now confidence-scaled, not a flat binary flag (2026-07-16 fix, carried into
  Notebook 12 when built)

## Corrections made after first-pass review (2026-07-16)

The first pass at Notebook 01 was reviewed against the project's established practices and `docs/03` before
continuing to Notebook 02. Two real gaps were found and fixed rather than carried forward:
1. `src/cpht/config.py` hand-duplicated legacy constants instead of importing them — fixed (see Structure section
   above).
2. The docs/03 Data Dictionary requirement wasn't scheduled anywhere in the 13-notebook mapping — fixed by building
   it in Notebook 01 (see mapping table above), since docs/03 explicitly calls it a prerequisite for Data Quality and
   Alert work.

This review-before-continuing step is now the expected pattern for each subsequent notebook, not a one-off: before
starting Notebook N+1, briefly check its planned scope against `docs/03`'s requirements for the areas it touches, not
just against the legacy notebook it's derived from.

## Next steps

1. Build Notebook 02 (Data Ingestion & Tag Mapping), verify against real data the same way Notebook 01 was, reading
   `data_dictionary.csv` + `data_profile.json` from Notebook 01 rather than re-deriving them.
2. Continue sequentially — each notebook should be built, executed against real data, and diffed against the
   legacy pipeline's equivalent output before moving to the next, so a discrepancy is caught immediately rather than
   compounding across 13 notebooks.
3. Notebook 03 must build the Data Quality Score (FR-DQ-012), not just relocate existing checks — see the mapping
   table note above.
4. Notebook 09 (Cleaning Event Detection) needs actual design discussion before it can be built, but has a concrete
   starting point (`export_cleaning_history.py`'s implicit heuristic, see mapping table) — flag this when reached,
   don't extract-and-move like the others.
