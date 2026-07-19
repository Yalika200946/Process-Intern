# Calculation Method Reference

**Status:** CURRENT

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

The strongest legacy candidate is `src/features/crude_properties.py` (was `notebooks/crude_properties.py`):

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

`Q_norm` is not approved as a fouling indicator. See `Q_NORM_AUDIT.md` for the full breakdown of its (at least) three conflicting formulas across the codebase.

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

## Appendix: duplicated-logic register

*(Merged in from the former `DUPLICATED_LOGIC_REGISTER.csv` — the full column set, including exact tags/formulas/filters per implementation, is preserved in git history if a row needs deeper inspection.)*

Every row below is a calculation family with more than one competing implementation in the active codebase. `Target owner section` is the section above that should become the single source of truth once the conflict is resolved; all rows carry status `REQUIRES_REVIEW`.

| ID | Family | Competing implementations | Core conflict | Target owner section |
|---|---|---|---|---|
| DL01 | Crude properties | 00 crude assay; `crude_properties.py`; `cpht_features.py`; NB02; NB08/schedulers/dashboard constants | Variable-property correlation vs. fixed `CP_CRUDE=2.2`/`RHO_CRUDE=850` shortcuts | Physical-property calculations |
| DL02 | Heat duty | NB02; NB04; NB09; `cpht_features.compute_q_features`; dashboard displays | E112C tag conflict; E101G unavailable; fixed vs. temperature/SG-dependent properties | HX thermal calculations → Heat duty |
| DL03 | Q_norm | NB02; NB04; `cpht_features`; cleaning-history CIT estimate; figures/dashboard | Denominator/interpretation differs by context; **not approved as a fouling indicator** | HX thermal calculations → Heat duty |
| DL04 | LMTD | Legacy feature/model code, incomplete current usage | Hot-side reconfiguration and missing sensors make many HX calculations invalid; no consistent mode filter | HX thermal calculations → LMTD and UA |
| DL05 | UA | NB02 U/UA proxy; `cpht_features`; scheduler comments; Rf calculations | Proxy called "U" may not be true overall U; design area/UA not incorporated | HX thermal calculations → LMTD and UA |
| DL06 | Fouling index | NB02/NB04 U_relative and Rf_run; Q deviation; Q_norm; NB12 delta_CIT | No single indicator — different indicators answer different questions but get mixed in rankings | Baseline and fouling calculations → Fouling indicators |
| DL07 | Fouling rate | NB02 rough rates; `nb_audit.robust_fouling_rate`; `compute_fouling_rate`; NB04 summaries; PHM | Tail-slope vs. whole-run/recent-slope selection differs downstream; only the robust version has reliability gates | Baseline and fouling calculations → Fouling rate |
| DL08 | Clean baseline | NB02 P90 run baseline; `compute_fouling_rate` state-aware P90; NB06 clean-duty model; NB12 post-TAM CIT model | Post-TAM cannot automatically mean clean; baseline levels answer HX-level and furnace-level questions separately | Baseline and fouling calculations → Clean-equivalent performance |
| DL09 | Cleaning-event detection | NB02 event_type/run reset; NB03 modes; `export_cleaning_history`; NB14; `cpht_features.get_tam_dates` | No full historical cleaning log; TAM whole-train attribution vs. switch-vs-clean ambiguity | Cleaning-event calculation |
| DL10 | CIT prediction | NB05 sensitivity; NB09/NB10 XGB/RF/LSTM; `gen_honest_metrics`; NB12 Ridge clean CIT | Targets/horizons not uniform; honest walk-forward shows **persistence wins**, SHAP models are attribution-only | Forecasting |
| DL11 | CIT deficit | NB12 delta_CIT; NB13 forecast deviation; scheduler network; NB16; dashboard | Clean-performance deficit, target deficit, and summed-HX deficit are not interchangeable | CIT and furnace calculations → CIT deficit |
| DL12 | Fuel-gas penalty | `export_economics` plant formula; legacy first-principles formula; scheduler FG conversion; NB16; dashboard JS | Two conflicting formulas with different prices/constants; dashboard duplicates the core calculation | CIT and furnace calculations → Furnace-duty and fuel-gas penalties |
| DL13 | Furnace headroom | `build_dashboard_topology`; `cleaning_scheduler_network`; tests; dashboard | Only FG_FLOW constrains the optimizer; other limits are mainly advisory and marked assumed | CIT and furnace calculations → Constraint headroom |
| DL14 | Forecasting | NB06; NB07; NB13; `add_forecast_intervals`; PHM; EOR | Multiple targets and experimental models mixed with operational forecasts; no unified baseline/horizon registry | Forecasting |
| DL15 | HX ranking | NB04; NB08; NB09; NB11; `export_engineering_priority`; NB13; NB16; schedulers | Different business questions presented as competing rankings; weights assumed, not approved | Priority and economics → Priority |
| DL16 | Economic benefit | NB12 gains; `export_economics`; NB16; schedulers; dashboard | Independent HX gains may over-add; price/cost dates and approved formulas unresolved | Priority and economics → Economic benefit |

## Dashboard contract

The dashboard may:

- filter, sort, chart, and display approved outputs;
- show method, units, uncertainty, freshness, and approval status.

It may not calculate:

- heat duty, LMTD, UA, fouling, CIT deficit;
- furnace/fuel penalties or headroom;
- forecasts, priority, payback, or economic benefit.

