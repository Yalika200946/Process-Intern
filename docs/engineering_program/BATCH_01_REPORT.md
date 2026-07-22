# Batch 1 — Formula, Unit, Area, F-Factor, and Property Completion

## Outcome

Status: `IMPLEMENTED_NOT_VALIDATED`

The canonical formula framework now includes bounded crude-property inputs, analytic integration of the current linear Cp correlation, generic mass-flow/enthalpy duty, uncertainty-explicit duty reconciliation, HX effectiveness, and finite/zero-safe energy closure. No blocked plant quantity was fabricated.

## Real-data execution

- 21,686 valid records across 15 HX were recalculated using analytic `integral Cp(T)dT`.
- The largest difference from the existing midpoint-Cp calculation was `2.46e-11 kW` (`1.83e-12%`), numerical roundoff only.
- This exact parity is expected because the current Cp correlation is linear in temperature.
- Qhot valid records: 0.
- Verified U records: 0.
- Effectiveness records: 0.
- Energy-closure records: 0.

## Registries

- `config/unit_registry.json`
- `config/property_model_registry.json`
- `config/area_and_f_registry.json`
- Runtime evidence: `reports/tables/mvp_real_data/full_engineering_program/batch_01/`

All 17 area/F records remain unverified. E107AB has `EXAMPLE_AREA_ONLY`; grouped and substituted equipment remain ambiguous or configuration-dependent. `F=1` remains `ASSUMPTION`. Therefore the program preserves UA and blocks verified U.

## Tests

Targeted formula/characterization/area tests: 73 passed.

Covered cases include property range validation, Cp integration parity, signed enthalpy, dimensional duty identity, uncertainty-weighted reconciliation, effectiveness bounds, energy closure, UA/U separation, example-area rejection, and F-status propagation.

## Blockers carried forward

- Qhot: approved hot-side mass flow and property/enthalpy basis.
- Reconciled Q: Qhot plus credible uncertainty estimates.
- Verified U: verified area, F, active-shell, and inside/outside area basis.
- Effectiveness: credible hot-side capacity rate.
- Energy closure: credible Qhot.

These blockers prevent formula-complete status but do not prevent Batch 2 cold-side data-quality and HX-performance work.
