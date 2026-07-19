# Q_norm Focused Audit

**Status:** CURRENT

## Executive finding

`Q_norm` is not one calculation in the current project. It is a reused name for at least three different quantities:

1. cold-side duty divided by total crude charge, using temperature- and SG-dependent properties;
2. fixed-property cold- or hot-side duty divided by total charge, with a scaled `dT/charge` proxy when flow is unavailable;
3. in `src/features/heat_duty.py` (was `notebooks/cpht_features.py`), a cold-side heat-capacity-rate term divided by charge, because `dT_cold` is missing from the implemented numerator.

The current Stage 07 contract correctly leaves its units as `REQUIRES_ENGINEERING_CONFIRMATION` and prohibits interpreting it as fouling before approval.

The detailed implementation register is in `reports/tables/q_norm_implementations.csv`.

## Usage coverage

The audit found Q_norm being:

- calculated in Stage 04, the legacy Stage 09 notebook, and `cpht_features.py`;
- renamed or converted into `mean_Q_norm`, `baseline_Q_norm`, `current_Q_norm`, `Q_shortfall`, and `CIT_sensitivity_degC_per_Qnorm`;
- plotted as daily/rolling performance, mean duty ranking, campaign status, Q–CIT scatter/correlation, and pipeline diagnostics;
- used as a CIT-model feature for every eligible non-E113A HX;
- not used directly as the CIT target, although E113A Q_norm would contain same-timestamp target leakage and is therefore explicitly excluded;
- used as a fouling indicator for slopes, percentage decline, cleaning jumps, and campaign baselines;
- used in CIT modeling through correlations, regressions, ML feature matrices, SHAP attribution, and clean counterfactuals;
- used in cleaning prioritization through Q shortfall, expected CIT gain, fouling rate, and priority scoring.

## 1. Active calculation used for fouling

Location: `notebooks/04_fouling_rate_estimation.ipynb`, cells 6 and 8.

The notebook calculates:

```text
Tavg = (Tin + Tout) / 2
Cp = (1.685 + 0.00339*Tavg) / sqrt(SG)
rho15.6 = SG * 999.016
alpha = 613.9723 / rho15.6^2
rho(Tavg) = rho15.6 * exp[-alpha*(Tavg-15.6)*(1+0.8*alpha*(Tavg-15.6))]
mass_flow = flow_m3h * rho(Tavg) / 3600
Q_kW = mass_flow * Cp * (Tout-Tin)
Q_norm = Q_kW / total_charge_m3h
```

- Numerator: calculated cold-side heat duty, kW.
- Denominator: `1fi005.pv`, total crude charge, m3/h.
- Resulting dimensional unit: `kW / (m3/h total charge)`.
- It is not dimensionless.

The notebook exports `Feature_Q.csv` and uses the same values for:

- fleet and per-HX plots;
- cleaning/switch detection from upward jumps;
- campaign fouling slopes;
- campaign baseline/current loss;
- `mean_Q_norm`;
- `Fouling_Rate_Ranking.csv`.

### Filtering

A value is retained only when:

- `dT_cold > 3 degC`;
- HX flow is greater than 10% of that HX's full-history mean;
- state is `NORMAL` or `SUBSTITUTE_ACTIVE`, if a state column exists.

If a state column is absent, the notebook assumes the HX is active. It does not independently reject a low total-charge denominator in the `Q_norm` calculation. It assumes shutdown periods were removed upstream.

### Embedded numerical evidence

The executed notebook reports mean `Q_norm` values from 2.676 to 30.075:

| HX | Mean Q_norm | Current | Campaign baseline | Active at final date |
|---|---:|---:|---:|---|
| E113A | 19.163 | 9.360 | 18.573 | Yes |
| E112C | 30.075 | 15.998 | 17.982 | No |
| E105AB | 12.809 | 15.401 | 15.174 | Yes |
| E103AB | 12.088 | 7.565 | 25.149 | Yes |
| E102 | 2.676 | 2.065 | 4.120 | Yes |

These embedded results do not show a normal operating mean near 100. Values approaching or exceeding 100 can nevertheless occur in unfiltered/raw records because the terminal formula can simplify to a large temperature-dependent value, and the unmasked duplicate implementation retains more transients.

## 2. Duplicate notebook calculation

Location: `notebooks/production/14_cit_model_feature_matrix.ipynb`, cells 10–12.

It implements:

```text
Q_norm = (850 * flow * 2.2 * dT / 3600) / total_charge
```

It also has two incompatible fallbacks:

```text
Q_norm_hot = (850 * hot_flow * 2.2 * dT_hot / 3600) / total_charge
Q_norm_proxy = dT_cold / total_charge * 100
```

The last formula is not duty and does not have the same units as the first two. The factor 100 is only a display scale.

This notebook:

- replaces only an exactly zero total-charge denominator with missing;
- does not apply the operating-state mask;
- clips each series to its own 1st–99th percentile only for plotting;
- treats declining `Q_norm` as fouling;
- infers cleaning events from upward jumps;
- uses `Q_norm` in CIT correlations and feature engineering.

Its embedded mean values differ from Stage 04, including E113A 15.045 and E112C 9.626. This confirms formula/configuration/filter drift.

## 3. Active shared CIT-feature defect

Location: `src/features/heat_duty.py` (was `notebooks/cpht_features.py`), `compute_q_features`, lines 189–224.

The cold-side branch currently implements:

```python
Q = rho_t * cold_flow * cp / 3600
Q_norm = Q / total_charge
```

The required `*(Tout-Tin)` term is absent. Therefore:

- `Q` is not heat duty;
- cold-side and hot-side branches have different dimensions;
- the function's docstring and variable names do not match the code;
- model features named `_Q_norm` do not represent the same quantity as `Feature_Q.csv`.

This implementation is active through `build_cit_feature_matrix()` and is consumed by:

- `notebooks/production/14_cit_model_feature_matrix.ipynb` Part 2 (was `15_cit_model_benchmark.ipynb`);
- `notebooks/production/14_cit_model_feature_matrix.ipynb` Part 3 (was `16_cit_shap_importance.ipynb`);
- `notebooks/12_economic_delta_cit.ipynb`;
- `pipeline/gen_honest_metrics.py`;
- saved CIT model and feature-column artifacts.

E113A's own `_Q_norm` is deliberately excluded from same-day CIT models because its outlet is the CIT target. E112C remains available as a feature and can use conflicting topology/tags.

## 4. Why E113A and E112C can appear much larger

### 4.1 Total-charge cancellation

In the fouling implementation, both E113A and E112C are configured with:

```text
cold flow = total charge
denominator = total charge
```

The flow ratio cancels:

```text
Q_norm_terminal
= [rho * total_charge * Cp * dT / 3600] / total_charge
= rho * Cp * dT / 3600
```

Other HXs commonly use one branch flow in the numerator but total plant charge in the denominator:

```text
Q_norm_branch = rho * Cp * dT / 3600 * (branch_flow / total_charge)
```

If a branch carries roughly one-third of total flow, its `Q_norm` is roughly one-third of a similar full-charge exchanger before considering different temperatures, services, and exchanger sizes. This is the main structural reason terminal values are larger.

For plausible `rho*Cp` near 1,800–2,500 kJ/(m3.K), a terminal `dT` of 100–150 degC gives approximately 50–104 kW/(m3/h). A value near 100 is therefore numerically possible without any kW/MW conversion error.

### 4.2 E113A/E112C duplication and topology conflict

In `src/domain/config.py` (was `notebooks/cpht_config.py`), E113A and E112C have exactly the same:

- cold flow: `1fi005.pv`;
- cold inlet: `1TI115.pv`;
- cold outlet: `1TI116.pv`.

Consequently their raw calculated Q and raw Q_norm are identical. The executed Stage 04 notebook confirms identical raw duty summary values:

- mean Q: 11,009.7 kW for both;
- standard deviation: 12,408.8 kW for both;
- maximum: 59,719.9 kW for both.

They differ only after separate operating-state masks and campaign segmentation are applied.

`src/features/heat_duty.py` (was `notebooks/cpht_features.py`) contains a conflicting E112C configuration using `1FI017.pv`, `1TI123.pv`, and `1TI114.pv`. Therefore the CIT-model E112C feature is not the same physical signal as the fouling-pipeline E112C signal.

Engineering review must resolve whether E112C is:

- a spare shell sharing the E113A terminal measurements; or
- a distinct upstream service with separate tags.

Until then, E112C/E113A comparisons are not physically traceable.

### 4.3 Combined A/B/C services

Names such as E110ABC and E112AB represent combined services while the ranking treats each configured name as one analytical HX. Their branch meters may serve a whole train branch or multiple exchangers in series. `Q_norm` retains exchanger size, number of shells, flow allocation and service arrangement; dividing by total charge does not normalize those effects.

Cross-HX level ranking is therefore a loading/size ranking, not a pure fouling comparison.

### 4.4 Bypass and offline periods

Stage 04 masks known `OFF`, `SUBSTITUTED`, and bypass-like states, but:

- missing state columns default to active;
- E112C and E113A depend heavily on state classification because their raw values are duplicated;
- the duplicate Stage 09 calculation has no state mask;
- the shared CIT-feature function has no state mask;
- low total charge is only protected against exact zero in some implementations.

Transient or misclassified periods can therefore produce large values and false jumps.

## 5. Requested discrepancy checks

| Check | Finding |
|---|---|
| kW versus MW | No evidence that the main Stage 04 formula mixes kW and MW. `/3600` correctly converts volumetric hourly flow to per-second mass flow when density is kg/m3. Labels consistently call Q kW. |
| kg/s versus t/h | Main Stage 04 uses kg/s consistently. No explicit t/h conversion was found in Q_norm. |
| Low/near-zero denominator | Exact zero is replaced only in the duplicate/model path. Stage 04 relies on upstream shutdown removal and has no local denominator floor. This remains a risk. |
| Combined A/B/C services | Present and not normalized away. Cross-HX values retain branch/shell configuration and size. |
| Bypass/offline periods | Stage 04 masks configured states; Stage 09 and `cpht_features.py` do not. |
| Sign convention | Stage 04 uses `Tout-Tin`; negative or small dT is removed by `dT>3`. Other implementations can retain negative dT before later `dropna` or clipping. |
| Different normalization formulas | Confirmed: variable-property duty, fixed-property duty, hot-side fallback, scaled dT proxy, and a missing-dT cold implementation coexist. |
| Missing-value replacement | Stage 04 masking yields missing. Stage 09 replaces zero charge with missing. `cpht_features.py` forward-fills crude assay and backfills only flagged lead-in rows; final model matrix drops missing rows. |
| Inconsistent crude-flow denominator | Confirmed structurally: numerator may use branch, total, hot-side, or no flow while denominator is total charge. E113A/E112C receive cancellation not shared by most HXs. |

## 6. Downstream impact

### Fouling and cleaning

`Feature_Q.csv` drives campaign jumps, fouling slopes, current Q loss and cleaning-event counts. The within-HX percentage decline is less sensitive to absolute HX scale than comparing mean Q_norm across HXs, but it is still vulnerable to mode changes, flow allocation, crude-property assumptions and false campaign boundaries.

### CIT modeling

`Q_CIT_Sensitivity.csv` fits independent same-period regressions of CIT on each HX's Q_norm. The resulting sensitivity is later multiplied by Q_norm shortfall. Since both terms use the same arbitrary Q_norm scale, some unit scaling can algebraically cancel, but formula, topology, filtering and confounding differences do not. Negative terminal correlations are already observed.

The ML model path is more serious: its active cold-side `_Q_norm` features omit dT and therefore do not match the fouling Q_norm or the documented physical interpretation.

### Cleaning prioritization and economics

The priority notebook uses:

```text
Q_shortfall = mean_Q_norm * Q_drop_pct / 100
expected_CIT_gain = Q_shortfall * CIT_sensitivity
```

It then combines normalized fouling rate and sensitivity in a priority score. These outputs inherit Q_norm's topology, formula and filtering conflicts. Model-based clean-counterfactual economics also inherit the `cpht_features.py` defect.

### Dashboard

The dashboard does not calculate Q_norm directly, but receives Q_norm sensitivity, Q-derived CIT consequence, cleaning history and priority outputs from pipeline exporters. It therefore publishes the downstream consequences of unresolved Q_norm logic.

## 7. Engineering interpretation and comparability

The current value can be interpreted only as a legacy, asset-specific performance proxy:

```text
calculated HX duty per unit total plant crude charge
```

It is not:

- dimensionless;
- normalized for exchanger area;
- normalized for branch-flow fraction;
- normalized for temperature driving force;
- a true UA or fouling resistance;
- directly comparable across HX configurations;
- approved as a fouling index.

Within one HX, one stable service mode, one consistent formula, and one crude/flow regime, a falling value may be consistent with performance degradation. It is not sufficient evidence of fouling by itself.

## 8. Audit conclusion

The project currently has:

- one legacy fouling Q_norm formula with useful operating-state gating but unapproved engineering interpretation;
- one duplicate notebook formula with fixed properties and mixed fallback units;
- one active shared model formula with a missing `dT` term;
- unresolved E112C topology;
- non-comparable branch-versus-total-flow scaling;
- downstream use in fouling, cleaning detection, CIT sensitivity, prioritization, economics and dashboard exports.

No single expected numerical range can be approved across all HXs because the current calculations do not represent one consistent physical quantity.

## Recommendation

**DO_NOT_USE**

Do not use current Q_norm values for engineering decisions, fouling conclusions, CIT attribution, cleaning ranking, or economics until one formula, topology, unit definition, operating-mode policy, low-flow rule, validation range, and uncertainty treatment are approved. Existing outputs may remain available only as clearly labeled legacy diagnostics.
