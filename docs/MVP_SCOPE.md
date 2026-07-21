# CPHT Fouling Analysis MVP Boundary

## Purpose

The reviewable MVP is an offline, read-only engineering analysis for the crude
preheat train. Its purpose is to establish a traceable calculation path from
aligned plant measurements to a basic indication of heat-exchanger fouling and
its first-order effect on crude inlet temperature (CIT).

This document defines the cleanup target. It does not claim that the current
production pipeline has already been reduced to this boundary.

## Four-step execution path

1. **Data ingestion, alignment, and quality**
   - Read the configured plant-data inputs without modifying the raw files.
   - Parse, sort, and align timestamps on one documented time basis.
   - Identify duplicate timestamps, missing intervals, non-finite values, and
     measurements outside configured physical ranges.
   - Produce explicit validity flags; do not silently manufacture valid data.

2. **HX thermal performance and operating mask**
   - Determine whether each exchanger observation is eligible for calculation
     using the minimum required operating-state mask.
   - Calculate crude properties, crude mass flow, cold-side heat duty, LMTD,
     and UA with explicit units and sign conventions.
   - Reject or flag invalid flow and invalid terminal-temperature conditions.

3. **Clean baseline and fouling indicator**
   - Select eligible clean-reference observations without using future data.
   - Calculate normalized UA relative to the clean baseline.
   - Report the fouling indicator separately from the clean baseline and UA.
   - Exclude invalid and out-of-service observations from the baseline and
     fouling calculations.

4. **Basic CIT impact**
   - Convert a recoverable heat-duty estimate to a first-order CIT effect using
     the documented crude mass-flow and heat-capacity basis.
   - Keep the result separate from forecasting, economics, recommendation
     scoring, and multi-exchanger network attribution.

## In scope

- Small deterministic inputs and hand-calculated test fixtures
- Data-quality and physical-validity flags
- Crude Cp and density correlations used by the current calculation path
- Mass-flow conversion and cold-side heat duty
- Counter-current LMTD and UA, including the stated correction-factor basis
- A clean-reference baseline, normalized UA, and a basic fouling indicator
- A first-order single-basis CIT impact calculation
- Unit and characterization tests for the calculations above

## Explicitly out of scope

- Forecasting and machine-learning model selection
- Survival analysis, RUL, or time-to-clean prediction
- Cleaning priority, scheduling, or optimization
- Economics and saving claims
- Shapley or multi-HX network attribution
- Advanced furnace modeling
- Governance or engineering-review report generation
- Recommendation scoring and action generation
- Dashboard, backend, or publishing logic
- Closed-loop control or DCS write-back

Out-of-scope code may remain in the repository during Phase 1. It is not part of
the intended MVP execution path and must not be required by the eventual MVP.

## Phase 1 change constraint

Phase 1 only preserves the full-system state, records this boundary, and adds
characterization tests for existing calculations. It must not consolidate
modules, change numerical formulas, delete notebooks or source code, modify the
production pipeline, generate reports or figures, or add engineering features.

