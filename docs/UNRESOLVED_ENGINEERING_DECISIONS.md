# Unresolved Engineering Decisions

## Release rule

Any item below blocks promotion of the affected calculation from candidate to approved source of truth. Until resolved, the register status remains `REQUIRES_ENGINEERING_CONFIRMATION`.

## 1. Crude properties

1. Approve the crude Cp correlation and its temperature/SG range.
2. Approve the density correlation and its range.
3. Decide whether fixed Cp/density fallbacks are permitted; if so, define when and how they are labeled.
4. Approve viscosity source, reference temperatures, interpolation, and extrapolation.
5. Select an enthalpy method: integrated Cp, simulator/property package, or another approved source.
6. Confirm crude assay effective timestamps and handling between assays.

## 2. Tags, topology, and mass balance

1. Resolve E112C topology and tags:
   - terminal spare sharing E113A measurements; or
   - separate upstream position/tags.
2. Confirm every shared-flow meter and its allocation rule.
3. Approve E101G mass-balance equation, service-state inference, tolerance, and confidence classes.
4. Define acceptable mass-balance residuals by operating mode.
5. **E101AB/E101CD sibling-branch state during E101EF↔E101G substitution
   (new, 2026-07-17):** `03_operating_state_classification.ipynb` sets
   `state['E101AB']`/`state['E101CD']` to `NORMAL` for the entire dataset
   except their own zero-flow days — neither is ever flagged during an
   `e101g_active` window, even though both share E101EF's cold-inlet tag
   `1TI102.pv` (three-way parallel branch off one common header,
   `cpht_config.HX_CONFIG`). The diagnostic cell added in notebook 03
   section 2.1 shows a real, synchronized level shift in both siblings when
   E101G comes active (E101AB: median `dT_cold` 51.4→48.4°C, `Q_norm`
   6.34→5.74; E101CD: 51.5→48.9°C, 5.33→5.01 — same direction, similar
   magnitude, over the single ~136-day 2026-01-18 substitution window in the
   current dataset). This is consistent with a three-branch flow-split
   effect when E101G comes online, not fouling — but the window runs to the
   end of the dataset, so there is no "after" period yet to separate a
   one-time topology-driven level shift from a genuine fouling trend with
   this data alone. Affects `08_cleaning_priority_ranking.ipynb`'s
   `worsening`/`trajectory_multiplier` term for E101AB, which is part of
   why E101AB currently ranks #5 in `engineering_priority_score`.
   **Decision needed:** should E101AB/E101CD be flagged (e.g.
   `SIBLING_SUBSTITUTED`) and excluded/down-weighted in
   `pipeline/compute_fouling_rate.py`'s in-service masking during
   `e101g_active` windows, the same way E101EF itself already is? Do not
   implement until confirmed — see notebook 03 §2.1 for the evidence to
   review.

**RESOLVED separately, 2026-07-17 — TAM-only HX false shell-switch
detection:** while reviewing the E101AB item above, confirmed (and fixed, by
plant-engineer instruction) an unrelated but confirmed bug: HX with
`bypass_config.BYPASS_CONFIG[hx]['online_mode'] == 'none'` (TAM-only, no
swap/online-clean capability at all — E103AB, E106AB, E107AB, E109AB) were
still going through `02_feature_engineering.ipynb`'s Q-jump-based
shell-switch detection (STEP 2), even though they physically cannot have a
mid-run "switch" outside a TAM. Before the fix: E107AB showed 17 detected
runs, E103AB 9, E109AB 8, E106AB 6 — against only ~2 real TAM events in the
dataset. Each false switch boundary fragmented one continuous fouling trend
into shorter regression windows, corrupting the fouling rate and
`08_cleaning_priority_ranking.ipynb`'s `trajectory_multiplier`/`worsening`
term for exactly these 4 HX. Fixed by skipping Q-jump detection entirely for
`online_mode == 'none'` HX (TAM dates and any real state transitions are
still honored) — after the fix all 4 show 3 runs (1 data-start + 2 TAM),
matching the actual TAM history. This is implemented, not open — see
`02_feature_engineering.ipynb` STEP 2 for the code and comment.

## 3. Heat-transfer calculations

1. Confirm heat-duty property method and units.
2. Confirm whether duty is cold-side only or may use reconciled hot/cold duty.
3. Approve the `Q_norm` formula, denominator, units, and permitted interpretation.
4. Identify HXs with sufficient tags for true LMTD.
5. Confirm flow arrangement and LMTD correction factors.
6. Confirm whether exchanger area/design UA data will be used.
7. Define true UA versus conductance proxy naming.
8. Approve energy-balance error denominator and acceptance range.

## 4. Clean reference and fouling

1. Define criteria for an acceptably clean HX/reference period.
2. Confirm whether any post-TAM period is approved and which equipment was actually cleaned.
3. Decide whether Stage 08 needs separate physical-reference and predictive clean-equivalent baselines.
4. Select approved fouling indicator(s): performance ratio, duty shortfall, Rf, or another.
5. Confirm whether `Q_norm` may ever be a fouling indicator.
6. Approve initiation-period length.
7. Approve rate estimator, curve candidates, minimum span/points, clipping, and reliability gates.
8. Select operational rate definition: tail, recent-window, or whole-run.

## 5. Cleaning events

1. Obtain or define the authoritative maintenance/cleaning log.
2. Approve event types and confidence tiers.
3. Define recovery thresholds and stable pre/post windows.
4. Confirm how shell swaps differ from actual cleaning.
5. Confirm TAM dates and whole-train attribution rules.

## 6. CIT and furnace impact

1. Confirm CIT target and floor.
2. Define which CIT deficit is used for monitoring, forecasting, and optimization.
3. Approve HX-to-CIT attribution method.
4. Confirm COT, fuel-gas flow, fuel-gas pressure, stack, O2, draft, and all four tube-skin limits.
5. Confirm warning/critical bands and limit direction.
6. Approve furnace-duty penalty formula.
7. Approve fuel-gas penalty formula and validate against `1FI028`.
8. Determine whether and how each furnace constraint can be forecast from CPHT degradation.

## 7. Forecasting

1. Define each operational target and forecast horizon.
2. Approve threshold definitions for cleaning and furnace risk.
3. Select required uncertainty level/coverage.
4. Define baseline acceptance criteria.
5. Approve scenario handling for future crude and operating rate.
6. Decide whether PHM Weibull, GP, power-law, and Monte Carlo models remain experimental.

## 8. Priority and scheduling

1. Approve condition, consequence, urgency, feasibility, and confidence components.
2. Approve weights and aggregation.
3. Decide whether partner-rate inheritance is permitted.
4. Confirm online, partial, swap-capable, and TAM-only classifications.
5. Confirm crew/resource caps, minimum spacing, annual frequency, and TAM calendar.
6. Approve reduced-form network interaction or specify a thermal-network model.
7. Define optimizer acceptance against simple and integer/metaheuristic baselines.

## 9. Economics

1. Approve physical energy/fuel saving method.
2. Confirm fuel price, units, effective date, and update process.
3. Confirm cleaning method costs, durations, variable costs, and downtime costs.
4. Approve operating days/year and discount/NPV basis.
5. Define calibration of modeled CIT gains.
6. Define network-interaction/additivity discount.
7. Define economic uncertainty/scenario reporting.

## 10. Approval-record requirements

For each resolution, record:

- decision ID;
- approved formula/method;
- units;
- applicable assets and operating range;
- configuration values;
- evidence/reference;
- approver name/role;
- approval date and review date;
- superseded decision, if any.

No notebook or dashboard change should be used as the approval record itself.

