"""Read-only real-data adapter and transparent MVP operating-state rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def load_pilot_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_dcs_matrix(config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the legacy DCS matrix without filling or changing source values."""
    spec = config["dataset"]
    raw = pd.read_excel(spec["path"], sheet_name=spec["sheet"], header=None)
    first = spec["first_tag_column"]
    tags = raw.iloc[spec["tag_row"], first:].astype(str).str.strip()
    units = raw.iloc[spec["unit_row"], first:].astype(str).str.strip()
    descriptions = raw.iloc[spec["description_row"], first:].astype(str).str.strip()
    metadata = pd.DataFrame({"source_tag": tags, "source_unit": units,
                             "description": descriptions})
    metadata = metadata[~metadata.source_tag.isin(("", "nan", "None"))].reset_index(drop=True)
    values = raw.iloc[spec["timestamp_data_row"]:, spec["timestamp_column"]:first + len(tags)].copy()
    values.columns = ["source_timestamp", *tags.tolist()]
    values["source_timestamp"] = pd.to_datetime(values["source_timestamp"], errors="coerce")
    values = values[values.source_timestamp.notna()].copy()
    values["timestamp"] = values.source_timestamp.dt.tz_localize(spec["timezone"], ambiguous="NaT", nonexistent="NaT")
    return values, metadata


def resolve_tag(columns, requested: str, aliases: dict[str, str]) -> str | None:
    target = aliases.get(requested, requested)
    exact = {str(c).casefold(): str(c) for c in columns}
    return exact.get(target.casefold())


def mapped_series(frame: pd.DataFrame, definition, aliases: dict[str, str]):
    """Return values, data kind, source tags, or an explicit unavailable result."""
    if isinstance(definition, str):
        source = resolve_tag(frame.columns, definition, aliases)
        if source is None:
            return pd.Series(np.nan, index=frame.index), "UNAVAILABLE", [definition]
        return pd.to_numeric(frame[source], errors="coerce"), "MEASURED", [source]
    method, tags = definition["method"], definition["tags"]
    resolved = [resolve_tag(frame.columns, tag, aliases) for tag in tags]
    if any(tag is None for tag in resolved):
        return pd.Series(np.nan, index=frame.index), "UNAVAILABLE", tags
    parts = pd.concat([pd.to_numeric(frame[tag], errors="coerce") for tag in resolved], axis=1)
    if method == "sum":
        return parts.sum(axis=1, min_count=len(parts.columns)), "CALCULATED", resolved
    if method == "row_max":
        return parts.max(axis=1, skipna=False), "INFERRED", resolved
    raise ValueError(f"Unsupported mapping method: {method}")


def classify_hx_records(frame: pd.DataFrame, hx_id: str, hx: dict[str, Any],
                        config: dict[str, Any]) -> pd.DataFrame:
    """Assign one documented state to every timestamp; never alter measurements."""
    rules, aliases = config["rules"], config["aliases"]
    out = pd.DataFrame({"timestamp": frame["timestamp"], "hx_id": hx_id})
    if hx["status"] in {"UNAVAILABLE", "BLOCKED"}:
        out["data_available"] = False
        out["operating_state"] = "UNAVAILABLE"
        out["operating_valid"] = False
        out["quality_warning_code"] = hx.get("unavailable_reason", hx.get("blocked_reason"))
        out["quality_reason"] = "HX mapping is not eligible for calculation."
        return out

    mapped = {}
    kinds = {}
    for name in ("cold_flow", "cold_in", "cold_out", "hot_in", "hot_out"):
        mapped[name], kinds[name], _ = mapped_series(frame, hx[name], aliases)
        out[name] = mapped[name].to_numpy()
        out[f"{name}_data_kind"] = kinds[name]
    numeric = out[["cold_flow", "cold_in", "cold_out", "hot_in", "hot_out"]]
    available = numeric.notna().all(axis=1) & np.isfinite(numeric).all(axis=1)
    temp_range = numeric[["cold_in", "cold_out", "hot_in", "hot_out"]].apply(
        lambda s: s.between(rules["temperature_min_c"], rules["temperature_max_c"])
    ).all(axis=1)
    cold_dt = out.cold_out - out.cold_in
    hot_dt = out.hot_in - out.hot_out
    terminal_1 = out.hot_in - out.cold_out
    terminal_2 = out.hot_out - out.cold_in
    physical = (cold_dt >= rules["cold_delta_t_min_c"]) & (hot_dt >= rules["hot_delta_t_min_c"]) \
        & (terminal_1 >= rules["terminal_delta_t_min_c"]) & (terminal_2 >= rules["terminal_delta_t_min_c"])
    shutdown = available & (out.cold_flow <= rules["flow_min_m3_h"])
    invalid = ~available | ~temp_range | (~shutdown & ~physical)
    startup = pd.Series(False, index=out.index)
    ended = shutdown.shift(1, fill_value=False) & ~shutdown
    for offset in range(rules["startup_records"]):
        startup |= ended.shift(offset, fill_value=False)
    flow_change = out.cold_flow.pct_change(fill_method=None).abs()
    temp_change = numeric[["cold_in", "cold_out", "hot_in", "hot_out"]].diff().abs().max(axis=1)
    steady = available & physical & ~shutdown & ~startup \
        & (flow_change <= rules["steady_flow_relative_change_max"]) \
        & (temp_change <= rules["steady_temperature_change_max_c"])
    state = np.select(
        [invalid, shutdown, startup, steady],
        ["INVALID_SENSOR", "SHUTDOWN", "STARTUP", "STEADY"], default="TRANSIENT")
    out["data_available"] = available
    out["operating_state"] = state
    out["operating_valid"] = state == "STEADY"
    codes, reasons = [], []
    warnings = hx.get("mapping_warnings", [])
    for i in out.index:
        if not available.loc[i]: code, reason = "MISSING_OR_NONFINITE_INPUT", "One or more required measurements are missing or non-finite."
        elif shutdown.loc[i]: code, reason = "FLOW_BELOW_OPERATING_MINIMUM", "Crude flow is at or below the configured operating threshold."
        elif not temp_range.loc[i]: code, reason = "TEMPERATURE_OUT_OF_RANGE", "A temperature is outside the configured engineering range."
        elif not physical.loc[i]: code, reason = "IMPOSSIBLE_TEMPERATURE_RELATIONSHIP", "Temperature differences do not meet HX physics thresholds."
        elif startup.loc[i]: code, reason = "STARTUP_STABILIZATION", "Record is within the configured post-shutdown startup period."
        elif not steady.loc[i]: code, reason = "TRANSIENT_OPERATION", "Flow or temperature change exceeds the steady-state threshold."
        else: code, reason = "", ""
        if warnings:
            code = "|".join(filter(None, [code, *warnings]))
            reason = " ".join(filter(None, [reason, "Mapping carries reviewed warning metadata."]))
        codes.append(code); reasons.append(reason)
    out["quality_warning_code"], out["quality_reason"] = codes, reasons
    return out


def candidate_stable_periods(physics: pd.DataFrame, rules: dict[str, Any]) -> pd.DataFrame:
    """Screen stable UA periods only; never label them clean or calculate a baseline."""
    rows = []
    n = rules["stable_window_records"]
    for hx_id, group in physics.groupby("hx_id"):
        g = group.sort_values("timestamp").reset_index(drop=True)
        eligible = g.operating_valid & g.ua_valid & g.ua_w_m2_k.notna()
        score = pd.DataFrame({
            "n": eligible.rolling(n).sum(),
            "ua_cv": g.ua_w_m2_k.rolling(n).std() / g.ua_w_m2_k.rolling(n).mean(),
            "flow_cv": g.cold_flow_m3_h.rolling(n).std() / g.cold_flow_m3_h.rolling(n).mean(),
            "temp_stability": g[["cold_in_c", "cold_out_c", "hot_in_c", "hot_out_c"]].rolling(n).std().mean(axis=1),
        })
        candidates = score[(score.n == n) & (score.ua_cv <= rules["stable_ua_cv_max"])
                           & (score.flow_cv <= rules["stable_flow_cv_max"])].copy()
        candidates["score"] = candidates.ua_cv + candidates.flow_cv + candidates.temp_stability / 100
        chosen = []
        for end_i, metrics in candidates.sort_values("score").iterrows():
            start_i = end_i - n + 1
            if any(not (end_i < a or start_i > b) for a, b in chosen):
                continue
            w = g.iloc[start_i:end_i + 1]
            rows.append({"hx_id": hx_id, "candidate_start": w.timestamp.iloc[0],
                         "candidate_end": w.timestamp.iloc[-1], "valid_record_count": int(n),
                         "median_ua_w_m2_k": float(w.ua_w_m2_k.median()),
                         "ua_variability_cv": float(metrics.ua_cv),
                         "crude_flow_variability_cv": float(metrics.flow_cv),
                         "temperature_stability_mean_std_c": float(metrics.temp_stability),
                         "evidence": "Operating-valid records with stable UA, flow, and temperatures.",
                         "exclusions": "Not evidence of cleaning; requires maintenance/TAM review.",
                         "status": "CANDIDATE"})
            chosen.append((start_i, end_i))
            if len(chosen) >= rules["stable_window_max_candidates"]:
                break
    return pd.DataFrame(rows)
