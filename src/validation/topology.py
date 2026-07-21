"""Fail-loud validation of CPHT topology and bypass configuration."""

from __future__ import annotations

from src.domain.config import CPHT_1_HX, CPHT_2_HX, HX_CONFIG, PARALLEL_SHELL_GROUPS


def validate_topology(bypass_config: dict | None = None) -> list[str]:
    errors: list[str] = []
    hx_all = CPHT_1_HX + CPHT_2_HX
    if len(hx_all) != len(set(hx_all)):
        errors.append("HX list contains duplicates")
    missing = sorted(set(hx_all) - set(HX_CONFIG) - {"E101G"})
    if missing:
        errors.append(f"HX missing cold-side configuration: {missing}")
    if "E101G" in HX_CONFIG:
        errors.append("E101G must not have direct measured temperature/flow configuration")
    for pair in PARALLEL_SHELL_GROUPS:
        if len(pair) != 2 or any(hx not in hx_all for hx in pair):
            errors.append(f"Invalid parallel-shell pair: {pair}")
            continue
        left, right = pair
        left_tags = {key: HX_CONFIG[left].get(key) for key in ("cold_flow", "cold_in", "cold_out")}
        right_tags = {key: HX_CONFIG[right].get(key) for key in ("cold_flow", "cold_in", "cold_out")}
        if left_tags != right_tags:
            errors.append(f"Parallel alternates {left}/{right} do not share cold-side tags")
    if bypass_config is not None:
        unknown = sorted(set(bypass_config) - set(hx_all))
        if unknown:
            errors.append(f"Bypass configuration contains unknown HX: {unknown}")
        for hx, row in bypass_config.items():
            mode, fraction = row.get("online_mode"), row.get("duty_fraction")
            if mode not in {"full", "partial", "none"}:
                errors.append(f"{hx} has invalid online_mode {mode!r}")
            if fraction is None or not 0 <= float(fraction) <= 1:
                errors.append(f"{hx} has invalid duty_fraction {fraction!r}")
    return errors


def topology_review_flags() -> list[str]:
    return ["TOPO-E112C-E113A", "INFER-E101G"]
