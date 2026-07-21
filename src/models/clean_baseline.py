"""Canonical clean-window UA baseline for the reviewable MVP.

The caller must supply the approved window explicitly.  This module does not
detect cleaning events, infer dates, fit models, or inspect records outside the
provided window.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def _invalid_baseline(unit: str, method: str, start, end, code: str, reason: str,
                      n_valid: int = 0) -> dict:
    return {
        "value": None,
        "clean_ua": None,
        "unit": unit,
        "basis": "approved clean-window UA",
        "data_kind": "CALCULATED",
        "baseline_method": method,
        "number_of_valid_records": int(n_valid),
        "baseline_start": pd.Timestamp(start).isoformat(),
        "baseline_end": pd.Timestamp(end).isoformat(),
        "warnings": (reason,),
        "quality": {"is_valid": False, "warning_code": code, "reason": reason},
    }


def calculate_clean_baseline(
    ua_values: Iterable[float],
    timestamps: Iterable,
    baseline_start,
    baseline_end,
    *,
    operating_valid: Iterable[bool] | None = None,
    method: str = "median",
    min_valid_records: int = 5,
    unit: str = "W/m2-K",
) -> dict:
    """Calculate clean UA from records inside one explicitly approved window."""
    if baseline_start is None or baseline_end is None:
        raise ValueError("baseline_start and baseline_end must be explicitly provided")
    start, end = pd.Timestamp(baseline_start), pd.Timestamp(baseline_end)
    if start > end:
        raise ValueError("baseline_start must not be after baseline_end")
    if method != "median":
        raise ValueError("MVP clean baseline supports only the approved median method")
    if min_valid_records <= 0:
        raise ValueError("min_valid_records must be positive")

    values = np.asarray(list(ua_values), dtype=float)
    index = pd.DatetimeIndex(pd.to_datetime(list(timestamps)))
    if len(values) != len(index):
        raise ValueError("ua_values and timestamps must have equal length")
    if operating_valid is None:
        operating = np.ones(len(values), dtype=bool)
    else:
        operating = np.asarray(list(operating_valid), dtype=bool)
        if len(operating) != len(values):
            raise ValueError("operating_valid must match ua_values length")

    in_window = np.asarray((index >= start) & (index <= end), dtype=bool)
    if not in_window.any():
        return _invalid_baseline(unit, method, start, end, "EMPTY_CLEAN_WINDOW",
                                 "No records fall inside the approved clean window.")
    if not (in_window & operating).any():
        return _invalid_baseline(unit, method, start, end, "INVALID_OPERATING_RECORD",
                                 "No operating-valid records fall inside the approved clean window.")

    finite = np.isfinite(values)
    positive = values > 0
    valid = in_window & operating & finite & positive
    clean_values = values[valid]
    if clean_values.size < min_valid_records:
        code = "INVALID_CLEAN_UA" if (in_window & operating & finite & ~positive).any() else "INSUFFICIENT_CLEAN_DATA"
        reason = ("Non-positive clean UA records prevent a valid baseline." if code == "INVALID_CLEAN_UA"
                  else f"Approved clean window has fewer than {min_valid_records} valid UA records.")
        return _invalid_baseline(unit, method, start, end, code, reason, clean_values.size)

    clean_ua = float(np.median(clean_values))
    excluded = int(in_window.sum() - clean_values.size)
    warnings = (() if excluded == 0 else
                (f"Excluded {excluded} non-finite, non-positive, or operating-invalid clean-window records.",))
    return {
        "value": clean_ua,
        "clean_ua": clean_ua,
        "unit": unit,
        "basis": "median UA inside explicitly approved clean window",
        "data_kind": "CALCULATED",
        "baseline_method": method,
        "number_of_valid_records": int(clean_values.size),
        "baseline_start": start.isoformat(),
        "baseline_end": end.isoformat(),
        "warnings": warnings,
        "quality": {"is_valid": True, "warning_code": None, "reason": None},
    }
