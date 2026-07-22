"""Transparent offline change screens; never confirmation of maintenance."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _robust_scale(values: pd.Series) -> float:
    finite = pd.to_numeric(values, errors="coerce").dropna()
    if finite.empty:
        return np.nan
    median = finite.median()
    mad = (finite - median).abs().median()
    return float(1.4826 * mad) if mad > 0 else float(finite.std(ddof=0))


def robust_step_screen(values, *, pre_records: int = 14, post_records: int = 14,
                       minimum_change: float = 0.05) -> pd.DataFrame:
    """Compare non-overlapping pre/post medians at every historical boundary."""
    series = pd.to_numeric(pd.Series(values), errors="coerce")
    pre = series.shift(1).rolling(pre_records, min_periods=pre_records).median()
    post = series.iloc[::-1].rolling(post_records, min_periods=post_records).median().iloc[::-1]
    change = post - pre
    return pd.DataFrame({"score": change, "candidate": change.ge(minimum_change),
                         "direction": np.where(change.ge(0), "RECOVERY", "DEGRADATION"),
                         "method": "ROBUST_MEDIAN_STEP", "uses_future_confirmation_window": True})


def cusum_recovery_screen(values, *, allowance: float = 0.005, threshold: float = 0.08) -> pd.DataFrame:
    """Past-only one-sided CUSUM of positive innovations from an expanding median."""
    series = pd.to_numeric(pd.Series(values), errors="coerce")
    baseline = series.shift(1).expanding(min_periods=14).median()
    innovation = series - baseline - allowance
    score = []
    running = 0.0
    for value in innovation:
        running = 0.0 if not np.isfinite(value) else max(0.0, running + float(value))
        score.append(running)
        if running >= threshold:
            running = 0.0
    score = pd.Series(score, index=series.index)
    return pd.DataFrame({"score": score, "candidate": score.ge(threshold), "direction": "RECOVERY",
                         "method": "CUSUM_POSITIVE_INNOVATION", "uses_future_confirmation_window": False})


def ewma_innovation_screen(values, *, span: int = 30, sigma_threshold: float = 3.0) -> pd.DataFrame:
    """Past-only EWMA innovation screen with robust scale."""
    series = pd.to_numeric(pd.Series(values), errors="coerce")
    prediction = series.shift(1).ewm(span=span, min_periods=14, adjust=False).mean()
    innovation = series - prediction
    scale = _robust_scale(innovation)
    score = innovation / scale if np.isfinite(scale) and scale > 0 else pd.Series(np.nan, index=series.index)
    return pd.DataFrame({"score": score, "candidate": score.ge(sigma_threshold), "direction": "RECOVERY",
                         "method": "EWMA_STATE_INNOVATION", "uses_future_confirmation_window": False})
