"""Engineering governance, approval metadata, and review-mode helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
GOVERNANCE_FILES = (
    CONFIG_DIR / "engineering_governance.json",
    CONFIG_DIR / "plant_limits.json",
    CONFIG_DIR / "economic_assumptions.json",
)
DATA_KINDS = {"MEASURED", "CALCULATED", "INFERRED", "PREDICTED", "ASSUMPTION"}
APPROVAL_STATUSES = {"CANDIDATE", "ASSUMPTION", "APPROVED", "TARGET_NOT_IMPLEMENTED"}


class GovernanceError(ValueError):
    pass


@dataclass(frozen=True)
class CalculationResult:
    value: Any
    unit: str | None
    basis: str
    data_kind: str
    confidence: str = "UNKNOWN"
    approval_status: str = "CANDIDATE"
    source_columns: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    quality: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.data_kind not in DATA_KINDS:
            raise GovernanceError(f"Invalid data kind: {self.data_kind}")
        if self.approval_status not in APPROVAL_STATUSES:
            raise GovernanceError(f"Invalid approval status: {self.approval_status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_registry(path: str | Path) -> dict[str, Any]:
    registry_path = Path(path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list):
        raise GovernanceError(f"Registry has no records list: {registry_path}")
    required = {"id", "status", "source", "approver", "approved_at", "review_due", "notes"}
    for index, record in enumerate(records):
        missing = required - set(record)
        if missing:
            raise GovernanceError(f"{registry_path.name} record {index} missing {sorted(missing)}")
        if record["status"] not in APPROVAL_STATUSES:
            raise GovernanceError(f"Invalid status for {record['id']}: {record['status']}")
        if record["status"] == "APPROVED" and not (record["approver"] and record["approved_at"]):
            raise GovernanceError(f"Approved record lacks approver/date: {record['id']}")
    return payload


def load_all_registries(paths: Iterable[str | Path] = GOVERNANCE_FILES) -> list[dict[str, Any]]:
    return [load_registry(path) for path in paths]


def approval_summary(registries: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
    active = list(registries) if registries is not None else load_all_registries()
    counts = {status: 0 for status in sorted(APPROVAL_STATUSES)}
    flags: list[str] = []
    for registry in active:
        for record in registry["records"]:
            counts[record["status"]] += 1
            if record["status"] != "APPROVED":
                flags.append(record["id"])
    return {
        "mode": "REVIEW",
        "counts": counts,
        "all_critical_approved": not flags,
        "assumption_flags": sorted(flags),
        "warning": "Engineering review output; candidate and assumed values are not plant-approved.",
    }


def config_hash(paths: Iterable[str | Path] = GOVERNANCE_FILES) -> str:
    digest = hashlib.sha256()
    for path in sorted((Path(p) for p in paths), key=lambda p: str(p)):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()
