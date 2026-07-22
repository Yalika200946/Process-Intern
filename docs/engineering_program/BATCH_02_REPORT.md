# Batch 2 — Data Quality, Validity Masks, and HX Performance

## Outcome

Status: `PROVISIONAL`

Eight explicit record-level masks are now generated without changing or deleting raw measurements:

- `data_valid`
- `steady_state_valid`
- `configuration_valid`
- `hx_calculation_valid`
- `baseline_fit_valid`
- `trend_fit_valid`
- `network_valid`
- `furnace_model_valid`

Every excluded record carries combined mask-exclusion reasons plus the original data-quality and configuration evidence.

## Execution

- 30,120 HX-timestamp records across 15 calculable HX.
- 21,686 cold-side calculation-valid records.
- Network-valid coverage is restricted to CPHT-2 timestamps that pass the existing mix-closure gate.
- E108AB, E112AB, and E113A receive zero baseline/trend/network eligibility under the conservative configuration mask because their residue configuration confidence is low.
- E101G and E112C remain outside the calculable 15-HX table and retain explicit unavailable/blocker records elsewhere.

## Data-quality checks

Validated: missing values, duplicate timestamps, sampling/gaps, flatline, range and temperature-physics checks.

Provisional/partial: rate-of-change, time alignment, sensor discontinuity, and configuration switching.

Blocked: direct maintenance state because a complete work-order history is unavailable.

## Evidence

Runtime outputs are under `reports/tables/mvp_real_data/full_engineering_program/batch_02/`.

The masks are suitable for conservative downstream screening. They do not validate inferred configuration or the full network.
