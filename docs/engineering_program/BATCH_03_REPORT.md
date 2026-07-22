# Batch 3 — Reference, Condition, Event, and Cycle Analysis

## Outcome

Status: `EXPLORATORY`

The confirmed-clean fields remain unavailable. The four existing empirical-reference HX were screened with three transparent offline methods:

- robust median step;
- positive-innovation CUSUM;
- EWMA state innovation.

## Execution

- Eligible HX: E101AB, E101CD, E102, and E104.
- De-duplicated detector candidates: 125.
- Fourteen-day consensus windows: 96.
- Confirmed cleaning events: 0.
- Confirmed cycles: 0.
- Confirmed fouling fields generated: false.

The high candidate count demonstrates method sensitivity and is not evidence of frequent cleaning. CUSUM in particular repeatedly responds after sustained level changes. Results are therefore method benchmarks and an engineering-review queue only.

## Semantic controls

- No candidate is classified `CONFIRMED_CLEANING`.
- Multi-method agreement may be labelled `CLEANING_RESPONSE_SUPPORTED_BUT_NOT_CONFIRMED` but is not usable as a confirmed cycle boundary.
- No degradation curve is fitted across these candidates.
- Survival analysis remains blocked because there are no confirmed cycles.

## Evidence

Runtime outputs are under `reports/tables/mvp_real_data/full_engineering_program/batch_03/`.
