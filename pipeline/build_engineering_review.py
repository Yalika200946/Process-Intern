"""Build the machine-readable Engineering Review Package from live sources of truth."""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.domain.bypass import BYPASS_CONFIG, feasibility_label
from src.domain.config import CPHT_1_HX, CPHT_2_HX, HX_CONFIG, PARALLEL_SHELL_GROUPS
from src.governance import GOVERNANCE_FILES, approval_summary, load_all_registries, utc_now
from src.validation.topology import topology_review_flags, validate_topology


OUT = ROOT / "dashboard" / "data" / "engineering_review.json"
REPORT_DIR = ROOT / "reports" / "engineering_review"

FURNACE_TAGS = {
    "CIT": ("1TI116.pv", "degC"), "COT": ("1TI150.pv", "degC"),
    "FG_FLOW": ("1FI028.pv", "t/h"), "FG_PRESSURE": ("1PC010.pv", "kg/cm2g"),
    "O2": ("1AI001.pv", "pct"), "DRAFT": ("1PC034.pv", "mmH2O"),
}


def build_tag_dictionary() -> list[dict]:
    rows: dict[str, dict] = {}
    for hx, config in HX_CONFIG.items():
        for role in ("cold_flow", "cold_in", "cold_out"):
            tag = config.get(role)
            if not tag:
                continue
            row = rows.setdefault(tag, {
                "tag_id": tag, "source_tag": tag, "canonical_name": role,
                "asset_ids": [], "measurement_type": "MEASURED", "unit_raw": None,
                "unit_canonical": "m3/h" if role == "cold_flow" else "degC",
                "valid_from": None, "valid_to": None, "approval_status": "CANDIDATE",
            })
            row["asset_ids"].append(hx)
    for name, (tag, unit) in FURNACE_TAGS.items():
        rows.setdefault(tag, {
            "tag_id": tag, "source_tag": tag, "canonical_name": name,
            "asset_ids": ["F101"], "measurement_type": "MEASURED", "unit_raw": None,
            "unit_canonical": unit, "valid_from": None, "valid_to": None,
            "approval_status": "CANDIDATE",
        })
    rows["E101G_FLOW_INFERRED"] = {
        "tag_id": "E101G_FLOW_INFERRED", "source_tag": None,
        "canonical_name": "E101G cold flow", "asset_ids": ["E101G"],
        "measurement_type": "INFERRED", "unit_raw": None, "unit_canonical": "m3/h",
        "valid_from": None, "valid_to": None, "approval_status": "CANDIDATE",
    }
    for row in rows.values():
        row["asset_ids"] = sorted(set(row["asset_ids"]))
    return sorted(rows.values(), key=lambda row: row["tag_id"])


def build_hx_register() -> list[dict]:
    parallel = {hx for pair in PARALLEL_SHELL_GROUPS for hx in pair}
    rows = []
    for hx in CPHT_1_HX + CPHT_2_HX:
        bypass = BYPASS_CONFIG.get(hx, {})
        rows.append({
            "hx_id": hx,
            "train_position": "CPHT-1" if hx in CPHT_1_HX else "CPHT-2",
            "swap_capable": hx in parallel,
            "tam_only": feasibility_label(hx) == "TAM_ONLY",
            "online_mode": bypass.get("online_mode", "none"),
            "duty_fraction": bypass.get("duty_fraction", 0.0),
            "sensor_coverage": "INFERRED" if hx == "E101G" else "COLD_SIDE_MEASURED",
            "flow_allocation_method": (HX_CONFIG.get(hx, {}).get("flow_source")
                                       or "dedicated meter" if hx != "E101G" else "mass-balance inference"),
            "approval_status": "CANDIDATE",
        })
    return rows


def main() -> None:
    topology_errors = validate_topology(BYPASS_CONFIG)
    package = {
        "schema_version": "1.0.0",
        "generated_at": utc_now(),
        "mode": "REVIEW",
        "approval_summary": approval_summary(),
        "topology_validation": {
            "structurally_valid": not topology_errors,
            "errors": topology_errors,
            "engineering_review_flags": topology_review_flags(),
        },
        "heat_exchangers": build_hx_register(),
        "tags": build_tag_dictionary(),
        "registries": load_all_registries(),
        "disclaimer": "Candidate review package; not an approved operating record.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "engineering_review.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (REPORT_DIR / "tag_dictionary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(package["tags"][0]))
        writer.writeheader()
        for row in package["tags"]:
            writer.writerow({**row, "asset_ids": ";".join(row["asset_ids"])})
    print(f"Wrote {OUT.name}: {len(package['heat_exchangers'])} HX, {len(package['tags'])} tags")


if __name__ == "__main__":
    main()
