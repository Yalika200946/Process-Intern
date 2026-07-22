# CPHT–F101 Independent Engineering Review Guide

## 1. Project purpose and engineering questions

The project is read-only decision support for crude-preheat-train heat-exchanger performance and its possible relationship to crude inlet temperature (CIT) and F101 consequences. It asks: Is the data usable? Which HX shows reduced thermal performance? Can operating conditions explain the change? Is there credible fouling evidence? What local or network temperature consequence is supported? What should be monitored or sent for engineering review?

It does **not** write to DCS, operate equipment, confirm cleaning without evidence, or guarantee savings.

## 2. Canonical architecture and data flow

```text
Plant historian / property inputs
  -> mapping, time alignment, quality and operating/configuration masks
  -> crude properties and mass flow
  -> Qcold, terminal differences, LMTD, apparent UA
  -> empirical reference or confirmed-clean baseline (different semantics)
  -> relative condition / confirmed fouling only when eligible
  -> HX-CIT screening and topology-gated network analysis
  -> furnace / forecast / decision layers when their hard gates pass
  -> immutable dashboard snapshot with status and provenance
```

The production execution truth remains the Codex pipeline. Dashboard-side calculations are presentation-only.

## 3. Current topology and configuration rules

The authoritative snapshot is `registries/configuration_topology.json`. CPHT-1 has grouped parallel E101 branches followed by E102. CPHT-2 has three crude-side branches. The residue-side order E113A -> E112C -> E112AB -> E108AB must not be confused with crude-side order. E101G substitutes for offline E101EF without equivalent direct instrumentation. E112C can substitute in residue cleaning configurations. There is no time-resolved valve/shell lineup history, so grouped-shell and configuration-dependent claims remain limited.

## 4–7. Formula, unit, property, area, and F-factor registries

- Formula definitions and required per-formula fields: `registries/formula_registry.csv` (39 formulas).
- Units: `registries/unit_registry.json`.
- Property correlations and approved range status: `registries/property_model_registry.json`.
- Transfer area and correction factor evidence: `registries/area_and_f_registry.json`.

`UA` calculated with candidate `F=1` is apparent conductance. Verified area-normalized `U` is blocked until transferable area, active-shell basis, and F are approved. The property model is provisional and has unquantified uncertainty.

## 8. Clean/reference semantics

The four post-TAM windows for E101AB, E101CD, E102, and E104 are empirical high-performance historical references only. They are not confirmed clean windows and TAM is not automatically a confirmed cleaning event.

```text
reference_ua_empirical = median(valid operating UA within provisional window)
relative_ua_empirical = UA_actual / reference_ua_empirical
relative_performance_loss = 1 - relative_ua_empirical
```

Values above reference are preserved and flagged. Canonical confirmed-clean fields remain unavailable until maintenance/clean-state evidence exists. See `outputs/empirical_reference_summary.csv`.

## 9. Condition and fouling indicators

Relative empirical loss is an exploratory performance comparison, not a confirmed fouling index. A confirmed normalized UA/fouling indicator requires a confirmed-clean baseline and eligible operating/configuration records. Apparent fouling resistance and rate calculations must inherit area/F, clean-state, and configuration limitations.

## 10. Cleaning-event definitions

See `registries/cleaning_event_registry.csv` and `cleaning_event_method_comparison.csv`. Signal events are candidates derived from operating signals, bypass feasibility, recovery patterns, and TAM context. TAM 2021/2024 are shutdown contexts, not automatic per-HX cleaning confirmations. Frequently cleanable residue HX remain review candidates, not confirmed records, without maintenance evidence.

## 11. Model registry and leaderboards

`registries/model_registry.csv` contains task, family, implementation, train/test scope, target, features, chronological validation, metrics, physical checks, selection status, rejection reason, and blocker. `model_leaderboard.csv` provides benchmark metrics. `BENCHMARK_ONLY` and `SELECTED_PROVISIONAL` do not authorize plant decisions. Advanced ML is not required merely to fill a registry.

## 12. Network equations and validation gates

The network layer uses split balance, enthalpy-weighted mixing, and sequential node-temperature propagation. Current CPHT-2 flow and mix closure are provisional. Full-network CIT is blocked because all branches, time-varying residue lineup, configuration history, and acceptable plant-approved error thresholds are not closed. See `registries/network_validation_gates.csv`, `outputs/network_status.json`, and `outputs/reconciliation_summary.json`.

## 13. Counterfactual definitions

A single-HX counterfactual replaces only the eligible HX performance state while keeping the declared scenario boundary fixed. Local equivalent temperature gain is not full-network CIT recovery. Pilot endpoint recovery is not furnace-inlet recovery unless the network endpoint and measured CIT are reproduced within approved tolerances. Multi-HX gains must not be added without an interaction-aware network method.

## 14. Furnace equations and basis

Core basis includes crude sensible duty and, where eligible, a candidate fuel penalty from duty divided by efficiency and fuel LHV. Furnace efficiency, LHV, operating limits, and measured fuel relationship must be explicitly sourced and approved. `outputs/furnace_estimate.csv` is provisional and cannot be presented as guaranteed fuel or economic saving.

## 15. Forecast definitions and validation

Forecasts require chronological out-of-sample validation against persistence, target/horizon-specific metrics, leakage checks, and physical-rule checks. Existing outputs are benchmarks/provisional screens; see `outputs/forecast_benchmark.csv` and model registries. A forecast must fall back to persistence or be rejected when it does not beat the baseline.

## 16. Decision and optimization prerequisites

Cleaning priority and schedule optimization require credible condition, network consequence, feasibility, operational constraints, economics, uncertainty, and human review. Current optimization readiness is in `outputs/optimization_readiness.csv`. Ranking output must not be treated as an operating instruction.

## 17. Dashboard data contract

See `registries/dashboard_data_contracts.yaml`, `dashboard_readiness.csv`, and `outputs/dashboard_snapshot_manifest.json`. Dashboard artifacts must share one generation ID and carry generated/data-as-of timestamps, schema version, source kind, approval/status, warnings, assumptions, confidence, and units. Mixed-generation data must be rejected or visibly warned. Browser formulas must not replace backend engineering calculations.

## 18–21. HX coverage, stage status, blockers, and tests

- HX-by-HX coverage: `registries/hx_by_hx_coverage.csv`.
- Stage maturity: `registries/stage_status.csv`.
- Blocking evidence: `registries/blocker_register.csv`.
- Test evidence: `evidence/targeted_test_results.json` and the repository test suite.
- Independent checks: `evidence/engineering_sense_check_register.csv` and `model_verification_register.csv`.

Coverage or output existence is not validation. Rows with zero valid records and configuration-dependent HX must remain explicitly unavailable or blocked.

## 22. Representative canonical outputs

The `outputs/` folder includes small review snapshots for reconciliation, empirical reference, network status, furnace estimate, forecast benchmark, optimization readiness, and the dashboard manifest. These are representative evidence only, not a complete rerunnable dataset.

## 23. Current dashboard screenshots

The `screenshots/` folder contains selected current views for General/Data Quality, HX Performance, Reference and Condition, Cleaning Events, HX-CIT, Network, Furnace, Forecast, and Decision. Screenshots demonstrate UI state only; they do not override registry maturity.

## 24. Prohibited claims

Do not claim:

- confirmed clean state or confirmed cleaning from TAM/signal evidence alone;
- confirmed fouling from empirical relative-performance loss;
- verified `U` while area, active shell basis, or F remains unapproved;
- full-network CIT recovery from a local or pilot-endpoint equivalent;
- causal HX-CIT effect from correlation or screening models;
- validated furnace fuel/savings impact using silent efficiency, LHV, or limit assumptions;
- validated forecast without chronological baseline comparison;
- optimal cleaning schedule without network consequence, feasibility, constraints, economics, and uncertainty;
- plant-ready decision support where the status is provisional, exploratory, blocked, or benchmark-only;
- equivalence to proprietary HTRI SmartPM algorithms or capability.

## Missing evidence requiring explicit resolution

1. Approved HX area, active-shell allocation, and LMTD correction factors.
2. Confirmed maintenance/cleaning history and clean-state evidence.
3. Time-resolved valve, bypass, split, shell, standby, and substitution history.
4. Approved hot-side flow and property basis for Qhot/energy closure.
5. Full CPHT branch propagation and measured CIT closure with approved thresholds.
6. Approved furnace efficiency, LHV, fuel tags, limits, and operating basis.
7. Time-based validated forecasting that beats persistence for the declared horizon.
8. Approved operational, economic, crew, bypass, and scheduling constraints.

