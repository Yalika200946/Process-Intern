# CPHT-F101 Fast-Track End-to-End Runbook

Safety snapshot: `safety/fast-track-20260722`  
Working branch: `fast-track/end-to-end-20260722`

Run from the repository root:

```powershell
python pipeline/run_fast_track_end_to_end.py
```

The command executes real-data validation, canonical HX physics, empirical-reference analysis, signal-event review, measured-CIT screening, network readiness, F101 consequence screening, empirical forecasts, decision support, the full test suite, and final report assembly.

Runtime outputs are written below `reports/tables/mvp_real_data/fast_track` and `reports/figures/mvp_real_data`. These paths are gitignored because they contain plant-derived values. Raw plant data are read-only and are never committed.

Status vocabulary is limited to `VALIDATED`, `PROVISIONAL`, `EXPLORATORY`, `PARTIAL`, `BLOCKED`, and `UNAVAILABLE`. A blocked stage does not stop independent supported stages.

The workflow does not establish confirmed HX cleaning, confirmed clean UA, full-network CIT recovery, fuel savings, or a final cleaning schedule unless their required evidence becomes available.
