"""Comparable-condition clean-equivalent baseline contract."""

import numpy as np

from src.governance import CalculationResult


def predict_clean_equivalent_performance(clean_reference_values, quantile=0.9):
    values = np.asarray(clean_reference_values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 5:
        raise ValueError("At least five eligible clean-reference values are required")
    return CalculationResult(
        value=float(np.quantile(values, quantile)), unit=None,
        basis=f"eligible clean-reference quantile P{int(quantile * 100)}",
        data_kind="PREDICTED", confidence="LOW", approval_status="CANDIDATE",
        source_columns=("approved_clean_reference_values",),
        warnings=("Clean-reference eligibility requires engineering confirmation.",),
        quality={"n_reference": int(values.size)},
    )

