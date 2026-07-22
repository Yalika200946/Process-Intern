# Batch 4 — Reference, Condition, and HX-CIT Model Benchmarks

## Outcome

Status: `PROVISIONAL`

A single chronological leaderboard now compares simple baselines with interpretable candidates. Selection requires lower holdout RMSE, no target leakage, and an open physical/semantic gate.

## Results

- Leaderboard rows: 34.
- Selected provisional: 5.
- Rejected: 14.
- Benchmark only: 15.
- Selected validated: 0.

Reference-performance Ridge models remain `BENCHMARK_ONLY` for all 15 HX because the metric uses unverified area/F and there is no confirmed clean state.

HX-CIT Ridge is selected provisionally for E101EF, E103AB, E109AB, and E112AB because it beats persistence. E113A is rejected despite favorable RMSE because its features carry CIT-derived target dependence. The remaining HX do not beat persistence.

The empirical linear condition trend is selected provisionally only for E101CD. E101AB, E102, and E104 are rejected in favor of persistence.

Advanced clean/fouling models and survival models are not fitted merely to fill the registry. Their semantic and confirmed-cycle prerequisites remain blocked.

## Evidence

Runtime outputs are under `reports/tables/mvp_real_data/full_engineering_program/batch_04/`.
