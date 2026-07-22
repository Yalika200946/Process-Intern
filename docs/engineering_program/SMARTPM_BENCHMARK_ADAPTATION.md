# SmartPM Conceptual-Benchmark Adaptation

## Decision

Use the reviewed SmartPM material only to improve dependency order, evidence semantics, and review UX. Do not copy proprietary algorithms, branding, graphical design, or claim equivalent capability.

## Implemented now

- A new reconciliation stage between configuration/mix validation and downstream interpretation.
- Raw measured values remain immutable and separate from reconciled values.
- An uncertainty-weighted CPHT-2 branch-flow balance pilot.
- A measured-versus-calculated mix-temperature reconciliation pilot.
- Explicit residual, adjustment, uncertainty, identifiability, status, and blocker outputs.
- A machine-readable SmartPM benchmark gap matrix.

## Real-data result

- Branch-flow reconciled timestamps: 1,953.
- Mix-temperature reconciled timestamps: 787.
- Median absolute normalized flow residual: 0.917.
- Median absolute normalized mix residual: 0.410.
- Mix records above the candidate 3-sigma screen: 4.70%.

All results are `PROVISIONAL`. The uncertainty weights are candidate assumptions rather than approved instrument accuracies, and the configuration model does not contain timestamped valve history.

## Hard-gate decision

The reconciliation pilot does not open inverse fouling-state estimation. Verified area, correction factor, clean thermal-resistance basis, and hot-side closure remain unavailable. It also does not open full-network simulation because E105AB mapping, E112C measurements, terminal lineup history, and measured-CIT reproduction remain unresolved.

Consequently, dynamic fouling is limited to existing empirical relative-performance benchmarks. Date-based network benefit, furnace attribution, economics, cleaning scheduling, and operator decision UI remain blocked.

## Required engineering inputs

1. Instrument uncertainty or calibration accuracy for total and branch flow and mix-temperature tags.
2. Timestamped CPHT-2 configuration and valve state.
3. Verified active area and F-factor by exchanger/configuration.
4. Hot-side flow and physical properties for energy closure.
5. Confirmed clean/design resistance basis for inverse fouling.
6. E105AB tag resolution, E112C data, and E113A/E112C lineup evidence.

Runtime evidence is generated under `reports/tables/mvp_real_data/reconciliation_pilot/`.
