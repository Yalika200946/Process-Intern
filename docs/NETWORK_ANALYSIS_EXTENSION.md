# CPHT Network Analysis Extension

This extension maps the supplied end-to-end CPHT concept onto the existing production
notebook chain. It does not create a second 00-30 notebook pipeline.

## Implemented first slice

- Local condition: historical clean-envelope Q_norm versus current 30-row median.
- Network consequence: audited single-HX CIT recovery from the existing economics/event path.
- Furnace consequence: CIT-equivalent avoided duty using the approved cold-side basis.
- Compensation ratio: diagnostic comparison of local Q loss and CIT-equivalent duty.
- Four plots: condition vs consequence, compensation ratio, CIT recovery ranking, and
  condition-consequence matrix.

The output is `CANDIDATE`. Pair/multi-HX interaction and temperature propagation are
explicitly `NOT_ESTIMATED`; single-HX recovery values must not be summed.

## Next gated slices

1. Fit clean-state models by operating mode and crude regime, with chronological validation.
2. Implement split/mix temperature propagation using measured hot-stream boundary conditions.
3. Backtest clean-one-HX counterfactuals against confirmed cleaning events.
4. Add pairwise interactions and Shapley attribution only after the single-HX model passes.
5. Replace the scheduler's additive reduced-form deficit only after network validation passes.
