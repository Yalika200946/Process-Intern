"""Hybrid empirical/datasheet CPHT network model.

The empirical track is the only track allowed to participate in temperature
propagation. Datasheet values are retained as diagnostic design references.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.domain.config import HX_CONFIG as COLD_CONFIG
from src.features.heat_duty import HX_CONFIG as FULL_CONFIG, parse_hx


CPHT2_BRANCHES = {
    "branch_15": ["E103AB", "E104", "E105AB"],
    "branch_16": ["E106AB", "E107AB", "E108AB", "E109AB"],
    "branch_17": ["E110ABC", "E111", "E112AB"],
}
TERMINAL_ALTERNATES = ("E113A", "E112C")
ALL_HX = list(COLD_CONFIG)[:3] + ["E101G", "E102"] + [hx for b in CPHT2_BRANCHES.values() for hx in b] + list(TERMINAL_ALTERNATES)


@dataclass
class EmpiricalHXModel:
    hx: str
    model: Any | None
    feature_tags: tuple[str, ...]
    cold_in_tag: str | None
    cold_out_tag: str | None
    cold_flow_tag: str | None
    n_train: int
    n_test: int
    mae_c: float | None
    baseline_mae_c: float | None
    accepted: bool
    status: str
    algorithm: str | None

    def predict_dt(self, row: pd.Series, cold_in_override: float | None = None) -> float | None:
        if self.model is None or self.cold_in_tag is None:
            return None
        values = []
        for tag in self.feature_tags:
            value = cold_in_override if tag == self.cold_in_tag and cold_in_override is not None else row.get(tag)
            if value is None or not np.isfinite(value):
                return None
            values.append(float(value))
        frame = pd.DataFrame([values], columns=self.feature_tags)
        return max(0.0, float(self.model.predict(frame)[0]))


def stream_config(hx: str) -> dict[str, str | None]:
    cold = COLD_CONFIG.get(hx, {})
    full = parse_hx(FULL_CONFIG[hx]) if hx in FULL_CONFIG else {}
    return {
        "cold_in": cold.get("cold_in"), "cold_out": cold.get("cold_out"),
        "cold_flow": cold.get("cold_flow"), "hot_in": full.get("hot_in"),
        "hot_flow": full.get("hot_flow"),
    }


def fit_empirical_models(process: pd.DataFrame, features: pd.DataFrame,
                         states: pd.DataFrame, min_train: int = 60) -> dict[str, EmpiricalHXModel]:
    """Fit chronological clean-state Ridge models for cold-side delta-T."""
    models: dict[str, EmpiricalHXModel] = {}
    for hx in ALL_HX:
        cfg = stream_config(hx)
        ci, co, flow = cfg["cold_in"], cfg["cold_out"], cfg["cold_flow"]
        if not ci or not co or not flow or ci not in process or co not in process or flow not in process:
            models[hx] = EmpiricalHXModel(hx, None, (), ci, co, flow, 0, 0, None, None, False, "INFERRED_ONLY" if hx == "E101G" else "INSUFFICIENT", None)
            continue
        candidate_tags = list(dict.fromkeys([ci, flow, "1fi005.pv"]))
        for tag in (cfg["hot_in"], cfg["hot_flow"]):
            if tag and tag in process and tag not in candidate_tags:
                candidate_tags.append(tag)
        frame = process[candidate_tags].copy()
        frame["target_dt"] = process[co] - process[ci]
        ucol = f"{hx}_U_relative"
        clean = features[ucol].reindex(frame.index) >= 0.90 if ucol in features else pd.Series(False, index=frame.index)
        if hx in states:
            clean &= states[hx].reindex(frame.index).isin(["NORMAL", "SUBSTITUTE_ACTIVE", "PARALLEL"])
        sample = frame.loc[clean].replace([np.inf, -np.inf], np.nan).dropna()
        sample = sample[(sample["target_dt"] > 0) & (sample["target_dt"] < 150)]
        if len(sample) < min_train:
            models[hx] = EmpiricalHXModel(hx, None, tuple(candidate_tags), ci, co, flow, len(sample), 0, None, None, False, "INSUFFICIENT_CLEAN_ROWS", None)
            continue
        split = max(min_train, int(len(sample) * 0.8))
        train, test = sample.iloc[:split], sample.iloc[split:]
        if test.empty:
            test = sample.iloc[-max(10, len(sample) // 5):]
            train = sample.iloc[:-len(test)]
        candidates = {
            "RIDGE": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
            "HIST_GRADIENT_BOOSTING": HistGradientBoostingRegressor(max_iter=150, max_depth=4, learning_rate=0.05, random_state=42),
        }
        fitted = []
        for name, estimator in candidates.items():
            estimator.fit(train[candidate_tags], train["target_dt"])
            pred = estimator.predict(test[candidate_tags])
            fitted.append((float(np.mean(np.abs(test["target_dt"].to_numpy() - pred))), name, estimator))
        mae, algorithm, estimator = min(fitted, key=lambda item: item[0])
        baseline = float(np.mean(np.abs(test["target_dt"].to_numpy() - train["target_dt"].median())))
        accepted = len(train) >= min_train and mae <= baseline and mae <= 5.0
        models[hx] = EmpiricalHXModel(hx, estimator, tuple(candidate_tags), ci, co, flow,
                                      len(train), len(test), mae, baseline, accepted,
                                      "ACCEPTED" if accepted else "CANDIDATE_FAILED_ACCEPTANCE", algorithm)
    return models


def active_terminal(state_row: pd.Series) -> str | None:
    active = [hx for hx in TERMINAL_ALTERNATES if state_row.get(hx) in {"NORMAL", "SUBSTITUTE_ACTIVE", "PARALLEL"}]
    return active[0] if len(active) == 1 else ("E113A" if not active else active[0])


def simulate_cpht2(row: pd.Series, feature_row: pd.Series, state_row: pd.Series,
                   models: dict[str, EmpiricalHXModel], clean_hx: set[str] | None = None,
                   terminal_override: str | None = None) -> dict:
    """Propagate CPHT-2 branch temperatures and mix before the active terminal shell."""
    clean_hx = clean_hx or set()
    inlet = row.get("1TI225.pv")
    if inlet is None or not np.isfinite(inlet):
        return {"cit": None, "status": "MISSING_CPHT2_INLET"}
    branch_results, weighted, total_flow = {}, 0.0, 0.0
    for name, path in CPHT2_BRANCHES.items():
        temp = float(inlet); steps = []; branch_flow = None
        for hx in path:
            model = models[hx]
            dt_clean = model.predict_dt(row, temp)
            actual_ci = row.get(model.cold_in_tag) if model.cold_in_tag else None
            actual_co = row.get(model.cold_out_tag) if model.cold_out_tag else None
            observed_dt = (float(actual_co) - float(actual_ci)
                           if actual_ci is not None and actual_co is not None and np.isfinite(actual_ci) and np.isfinite(actual_co) else None)
            clean_at_actual = model.predict_dt(row, float(actual_ci)) if actual_ci is not None and np.isfinite(actual_ci) else None
            factor = (float(np.clip(observed_dt / clean_at_actual, 0, 1.25))
                      if observed_dt is not None and clean_at_actual is not None and clean_at_actual > 0 else 1.0)
            if hx in clean_hx and dt_clean is not None:
                dt = dt_clean
            elif dt_clean is not None:
                dt = dt_clean * factor
            else:
                dt = observed_dt
            if dt is not None: temp += dt
            if branch_flow is None and model.cold_flow_tag:
                branch_flow = row.get(model.cold_flow_tag)
            steps.append({"HX": hx, "tin_c": round(temp - (dt or 0), 4), "tout_c": round(temp, 4),
                          "dt_clean_c": None if dt_clean is None else round(dt_clean, 4),
                          "observed_dt_c": None if observed_dt is None else round(observed_dt, 4),
                          "condition_factor": round(factor, 4)})
        flow = float(branch_flow) if branch_flow is not None and np.isfinite(branch_flow) and branch_flow > 0 else 0.0
        branch_results[name] = {"flow_m3_h": flow, "outlet_c": round(temp, 4), "steps": steps}
        weighted += temp * flow; total_flow += flow
    calculated_mixed = weighted / total_flow if total_flow > 0 else float(np.mean([v["outlet_c"] for v in branch_results.values()]))
    measured_mixed = row.get("1TI115.pv")
    mix_bias = (float(measured_mixed) - calculated_mixed
                if measured_mixed is not None and np.isfinite(measured_mixed) else 0.0)
    mixed = calculated_mixed + mix_bias
    terminal = terminal_override or active_terminal(state_row)
    terminal_model = models.get(terminal) if terminal else None
    terminal_dt_clean = terminal_model.predict_dt(row, mixed) if terminal_model else None
    terminal_actual_ci = row.get(terminal_model.cold_in_tag) if terminal_model else None
    terminal_actual_co = row.get(terminal_model.cold_out_tag) if terminal_model else None
    terminal_observed_dt = (float(terminal_actual_co) - float(terminal_actual_ci)
                            if terminal_actual_ci is not None and terminal_actual_co is not None and np.isfinite(terminal_actual_ci) and np.isfinite(terminal_actual_co) else None)
    terminal_clean_actual = terminal_model.predict_dt(row, float(terminal_actual_ci)) if terminal_model and terminal_actual_ci is not None and np.isfinite(terminal_actual_ci) else None
    factor = (float(np.clip(terminal_observed_dt / terminal_clean_actual, 0, 1.25))
              if terminal_observed_dt is not None and terminal_clean_actual is not None and terminal_clean_actual > 0 else 1.0)
    if terminal in clean_hx and terminal_dt_clean is not None:
        terminal_dt = terminal_dt_clean
    elif terminal_dt_clean is not None:
        terminal_dt = terminal_dt_clean * factor
    else:
        terminal_dt = terminal_observed_dt or 0.0
    cit = mixed + terminal_dt
    return {"cit": round(cit, 4), "status": "OK", "cpht2_inlet_c": round(float(inlet), 4),
            "branches": branch_results, "calculated_mixed_c": round(calculated_mixed, 4),
            "mix_balance_correction_c": round(mix_bias, 4), "mixed_c": round(mixed, 4), "active_terminal": terminal,
            "terminal_dt_clean_c": None if terminal_dt_clean is None else round(terminal_dt_clean, 4),
            "terminal_condition_factor": round(factor, 4)}


def counterfactuals(row: pd.Series, feature_row: pd.Series, state_row: pd.Series,
                    models: dict[str, EmpiricalHXModel]) -> tuple[list[dict], list[dict]]:
    base = simulate_cpht2(row, feature_row, state_row, models)
    base_cit = base.get("cit")
    singles = []
    for hx in [h for b in CPHT2_BRANCHES.values() for h in b] + list(TERMINAL_ALTERNATES):
        override = hx if hx in TERMINAL_ALTERNATES else None
        result = simulate_cpht2(row, feature_row, state_row, models, {hx}, terminal_override=override)
        gain = None if base_cit is None or result.get("cit") is None else result["cit"] - base_cit
        singles.append({"HX": hx, "cit_recovery_c": None if gain is None else round(max(0.0, gain), 4),
                        "model_status": models[hx].status, "approval_status": "CANDIDATE"})
    interactions = []
    usable = [r["HX"] for r in singles if r["cit_recovery_c"] is not None]
    single_map = {r["HX"]: r["cit_recovery_c"] for r in singles}
    for i, a in enumerate(usable):
        for b in usable[i + 1:]:
            if a in TERMINAL_ALTERNATES and b in TERMINAL_ALTERNATES:
                continue
            override = a if a in TERMINAL_ALTERNATES else (b if b in TERMINAL_ALTERNATES else None)
            pair = simulate_cpht2(row, feature_row, state_row, models, {a, b}, terminal_override=override)
            pair_gain = pair["cit"] - base_cit
            interactions.append({"hx_a": a, "hx_b": b, "pair_recovery_c": round(max(0.0, pair_gain), 4),
                                 "interaction_c": round(pair_gain - single_map[a] - single_map[b], 4)})
    return singles, interactions
