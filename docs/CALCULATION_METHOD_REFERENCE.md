# Calculation Method Reference

## Purpose

This reference accompanies `SOURCE_OF_TRUTH_REGISTER.csv`. It defines the target calculation boundaries without promoting unresolved legacy formulas to approved engineering truth.

Status `REQUIRES_ENGINEERING_CONFIRMATION` means one or more of the formula, tags, operating range, assumptions, limits, or acceptance thresholds has not been approved in the available project record.

## Mandatory implementation rules

1. Each registered calculation has one target function.
2. Notebooks call the target function; they do not reproduce its formula.
3. Stage 15 and the dashboard never perform core calculations.
4. Functions return units, lineage, method/version, validity, and uncertainty metadata.
5. Invalid or unavailable values return a reason, not a silent zero.
6. Measured, calculated, inferred, and assumed inputs remain distinguishable.
7. Engineering constants are loaded from approved configuration, not function literals.

## Physical-property calculations

### Crude density and Cp

The strongest legacy candidate is `notebooks/crude_properties.py`:

```text
Cp = (1.685 + 0.00339 T) / sqrt(SG)

rho_15.6 = SG × 999.016
alpha = 613.9723 / rho_15.6²
rho_T = rho_15.6 × exp[-alpha(T - 15.6)(1 + 0.8 alpha(T - 15.6))]
```

These formulas remain candidates because no approved correlation range or plant comparison is documented. Fixed legacy values such as `Cp=2.2 kJ/kg-K` and `rho=850 kg/m3` must not coexist as unmarked alternatives.

### Viscosity and enthalpy

No complete approved viscosity or enthalpy method was found. Stage 06 must either:

- use measured assay values with effective dating; or
- adopt a correlation/property package after engineering confirmation.

Heat duty should prefer mass flow multiplied by an approved enthalpy difference. The `Cp × deltaT` form may remain an explicitly named approximation if approved.

## Flow and equipment-state calculations

### Mass balance and E101G

E101G has no direct sensors. Any E101G flow or state is inferred and must include:

- input tags;
- governing branch equation;
- operating-mode assumptions;
- balance residual;
- confidence tier.

The inference may not be stored under a measured-value column.

## HX thermal calculations

### Heat duty

Candidate general form:

```text
Q = mass_flow × (h_out - h_in) / 3600
```

Legacy approximation:

```text
Q = volumetric_flow × density × Cp × (T_out - T_in) / 3600
```

Output is kW when flow is m3/h, density kg/m3, Cp kJ/kg-K, and temperature difference K.

Approval is still required for:

- property method;
- E112C tags/topology;
- shared-flow meter treatment;
- operating filters;
- use of the approximation rather than enthalpy.

### LMTD and UA

The target distinguishes true LMTD/UA from cold-side proxies.

Candidate counter-current LMTD:

```text
LMTD = (deltaT1 - deltaT2) / ln(deltaT1 / deltaT2)
```

Candidate UA:

```text
UA = Q / (F × LMTD)
```

The correction factor `F`, flow arrangement, valid temperature ordering, and sensor sufficiency require confirmation. `Q / cold-side deltaT` must be named a conductance proxy, not UA.

### Energy-balance error

The target will report signed and relative hot/cold duty disagreement. The relative-error denominator and acceptance band remain unresolved.

## Baseline and fouling calculations

### Clean-equivalent performance

Legacy methods answer different questions:

- first-run-window P90 estimates a per-run reference;
- state-aware P90 improves service filtering;
- predictive clean-Q models adjust for load/crude;
- post-TAM clean-CIT modeling estimates furnace-level potential.

They must not share one ambiguous “clean baseline” label. Stage 08 will register the target quantity, clean reference, model, validation, and uncertainty.

Post-TAM status alone is insufficient evidence of a perfectly clean train.

### Fouling indicators

Potential indicators remain separate:

```text
performance_ratio = actual_performance / clean_equivalent_performance
duty_shortfall = clean_equivalent_duty - actual_duty
Rf_proxy = 1 / UA_actual - 1 / UA_clean
```

`Q_norm` is not approved as a fouling indicator.

### Fouling rate

The strongest legacy candidate is `nb_audit.robust_fouling_rate`:

- in-service filtering;
- initiation-phase exclusion;
- isolated-spike and recovery-jump handling;
- Theil–Sen slope and confidence interval;
- linear versus asymptotic curve selection by AIC;
- tail slope as current rate;
- fit/noise/oscillation/span/Rf reliability gates.

Engineering must confirm all thresholds and whether tail, recent-window, or whole-run slope is the operational rate.

## Cleaning-event calculation

The target event score combines independent evidence:

- confirmed maintenance/TAM record;
- mode or shell transition;
- performance recovery;
- stable pre/post event windows;
- simultaneous-HX evidence for TAM.

Whole-train TAM recovery must not be attributed to one HX. A score/threshold is not yet approved.

## CIT and furnace calculations

### CIT deficit

The target preserves distinct definitions:

```text
target_deficit = CIT_target - CIT_measured
clean_equivalent_deficit = CIT_clean_equivalent - CIT_measured
```

Whether negative values are retained or clipped depends on the named output. Summing independently modeled HX deficits is not approved.

### Furnace-duty and fuel-gas penalties

Two legacy fuel methods conflict:

1. Plant empirical energy coefficient using `STD_ENERGY × Feed_KBD × deltaC`.
2. First-principles mass-energy balance using charge, density, Cp, LHV, and furnace efficiency.

Neither is selected. Stage 11 should first calculate physical energy/fuel impact; Stage 14 applies dated economic prices.

### Constraint headroom

For an upper limit:

```text
headroom = limit - value
```

For a lower limit:

```text
headroom = value - limit
```

The generic convention is acceptable, but every limit, direction, warning band, and forecast relationship requires engineering configuration. All four tube-skin passes must remain separate.

## Forecasting

There is no approved single forecast model. The canonical contract requires:

- one declared target and horizon;
- only information available at forecast origin;
- chronological walk-forward validation;
- a simple baseline;
- uncertainty intervals/distributions;
- candidate-model rejection or baseline fallback when it does not outperform.

Current CIT tree/LSTM models fail to beat persistence in honest validation and therefore remain experimental/attribution-only.

## Priority and economics

### Priority

The target score must expose condition, consequence, urgency, feasibility, confidence, and reason codes. Weighting and aggregation are unresolved. A risk ranking and constrained schedule are distinct products.

### Economic benefit

The canonical structure will combine approved physical savings, dated prices, cleaning/downtime costs, and uncertainty. Measured event gains should be preferred when attributable; modeled values require calibration and provenance.

Independent HX gains cannot be added without an approved network-interaction treatment.

## Dashboard contract

The dashboard may:

- filter, sort, chart, and display approved outputs;
- show method, units, uncertainty, freshness, and approval status.

It may not calculate:

- heat duty, LMTD, UA, fouling, CIT deficit;
- furnace/fuel penalties or headroom;
- forecasts, priority, payback, or economic benefit.

