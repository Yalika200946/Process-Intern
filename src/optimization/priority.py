"""Separate condition ranking from action recommendation."""

from __future__ import annotations


LOW_CONFIDENCE = {"LOW", "UNKNOWN", "UNRELIABLE", "UNCERTAIN"}


def recommend_action(condition_score: float, confidence: str, online_mode: str) -> dict:
    confidence = str(confidence or "UNKNOWN").upper()
    mode = str(online_mode or "none").lower()
    if confidence in LOW_CONFIDENCE:
        action = "INVESTIGATE"
    elif mode == "none":
        action = "PLAN_FOR_TAM" if condition_score > 0 else "MONITOR"
    elif condition_score > 0:
        action = "CLEAN"
    else:
        action = "MONITOR"
    return {
        "action": action,
        "condition": {"score": float(condition_score)},
        "confidence": confidence,
        "feasibility": {"online_mode": mode},
        "required_human_review": True,
        "approval_status": "CANDIDATE",
    }


def online_recoverable_gain(full_gain: float, duty_fraction: float) -> float:
    if not 0 <= duty_fraction <= 1:
        raise ValueError("duty_fraction must be between zero and one")
    return float(full_gain) * float(duty_fraction)

