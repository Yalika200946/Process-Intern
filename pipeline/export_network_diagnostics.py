"""Export local-condition/network-consequence diagnostics and engineering plots."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.network.attribution import build_network_diagnostics

DATA_DIR = Path(os.environ.get("CPHT_DATA_DIR", r"C:\Desktop\Bangchak Internship 2026\Data"))
DASH = ROOT / "dashboard" / "data"
FIGURES = ROOT / "figures" / "network_diagnostics"


def _condition_rows(feature_q: pd.DataFrame) -> list[dict]:
    rows = []
    for hx in feature_q.columns:
        series = pd.to_numeric(feature_q[hx], errors="coerce").dropna()
        rows.append({
            "HX": hx,
            "clean_q_norm": None if series.empty else float(series.quantile(0.90)),
            "current_q_norm": None if series.empty else float(series.tail(min(30, len(series))).median()),
        })
    return rows


def _save_plots(rows: list[dict]) -> list[str]:
    FIGURES.mkdir(parents=True, exist_ok=True)
    colors = {"HIGH": "#168aad", "MEDIUM": "#52b788", "LOW": "#f4a261", "INSUFFICIENT": "#adb5bd"}
    paths: list[str] = []

    valid = [r for r in rows if r["local_q_loss_mw"] is not None and r["marginal_cit_recovery_c"] is not None]
    fig, ax = plt.subplots(figsize=(9, 6))
    for row in valid:
        ax.scatter(row["local_q_loss_mw"], row["marginal_cit_recovery_c"], color=colors[row["confidence"]], s=65)
        ax.annotate(row["HX"], (row["local_q_loss_mw"], row["marginal_cit_recovery_c"]), xytext=(4, 4), textcoords="offset points", fontsize=8)
    ax.set(xlabel="Local Q loss (MW, candidate clean envelope)", ylabel="Single-HX CIT recovery (°C)", title="Local condition vs network consequence")
    ax.grid(alpha=.25)
    path = FIGURES / "condition_vs_consequence.png"; fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig); paths.append(str(path.relative_to(ROOT)))

    comp = sorted([r for r in rows if r["compensation_ratio"] is not None], key=lambda r: r["compensation_ratio"])
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh([r["HX"] for r in comp], [r["compensation_ratio"] for r in comp], color="#457b9d")
    ax.axvline(0, color="black", lw=.8); ax.axvline(1, color="#e76f51", lw=.8, ls="--")
    ax.set(xlabel="Compensation ratio (diagnostic)", title="Estimated downstream compensation")
    path = FIGURES / "compensation_ratio.png"; fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig); paths.append(str(path.relative_to(ROOT)))

    ranked = sorted([r for r in rows if r["marginal_cit_recovery_c"] is not None], key=lambda r: r["marginal_cit_recovery_c"], reverse=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar([r["HX"] for r in ranked], [r["marginal_cit_recovery_c"] for r in ranked], color=[colors[r["confidence"]] for r in ranked])
    ax.set(ylabel="CIT recovery (°C)", title="Single-HX marginal CIT recovery and confidence")
    ax.tick_params(axis="x", rotation=55)
    path = FIGURES / "cit_recovery_by_hx.png"; fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig); paths.append(str(path.relative_to(ROOT)))

    matrix_rows = [r for r in valid if r["condition_loss_fraction"] is not None]
    fig, ax = plt.subplots(figsize=(9, 6))
    x = np.array([r["condition_loss_fraction"] * 100 for r in matrix_rows]); y = np.array([r["marginal_cit_recovery_c"] for r in matrix_rows])
    ax.scatter(x, y, c=y, cmap="viridis", s=70)
    for row, xi, yi in zip(matrix_rows, x, y):
        ax.annotate(row["HX"], (xi, yi), xytext=(4, 3), textcoords="offset points", fontsize=8)
    ax.set(xlabel="Local condition loss (%)", ylabel="Marginal CIT consequence (°C)", title="Condition–consequence matrix")
    ax.grid(alpha=.25)
    path = FIGURES / "condition_consequence_matrix.png"; fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig); paths.append(str(path.relative_to(ROOT)))
    return paths


def main() -> None:
    feature_q = pd.read_csv(DATA_DIR / "Feature_Q.csv", index_col=0)
    economics = json.loads((DASH / "economics.json").read_text(encoding="utf-8"))
    consequence = {row["HX"]: row for row in economics.get("per_hx", [])}
    rows = build_network_diagnostics(_condition_rows(feature_q), consequence, charge_m3_h=float(economics["charge_m3h"]))
    payload = {
        "schema_version": "1.0.0", "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "Observed Q_norm condition joined to audited single-HX CIT recovery",
        "method_status": "CANDIDATE", "network_model_status": "DIAGNOSTIC_NOT_FULL_THERMAL_DIGITAL_TWIN",
        "interaction_status": "PAIR_AND_MULTI_HX_INTERACTIONS_NOT_ESTIMATED",
        "basis": {"clean_q_norm": "historical 90th percentile", "current_q_norm": "latest 30-row median"},
        "warnings": ["Do not sum single-HX CIT recoveries to estimate multi-HX benefit.",
                     "Compensation ratio remains diagnostic until event backtesting passes."],
        "rows": rows, "plots": _save_plots(rows),
    }
    (DASH / "network_diagnostics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote network_diagnostics.json: {len(rows)} HX, {len(payload['plots'])} plots")


if __name__ == "__main__":
    main()
