"""Append-only, unauthenticated local review log for cleaning-event candidates."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_DECISIONS = {"CONFIRM", "REJECT", "RECLASSIFY"}
ALLOWED_CLASSES = {
    "CONFIRMED_CLEAN", "REJECTED_EVENT", "CONFIRMED_TAM", "SWITCH_CANDIDATE",
    "UNEXPLAINED_RECOVERY",
}


def default_audit_path() -> Path:
    data = Path(os.environ.get("CPHT_DATA_DIR", r"C:\Desktop\Bangchak Internship 2026\Data"))
    return data / "Cleaning_Event_Review_Audit.jsonl"


def append_review(review: dict[str, Any], path: str | Path | None = None) -> dict[str, Any]:
    event_id = str(review.get("event_id") or "").strip()
    decision = str(review.get("decision") or "").upper()
    note = str(review.get("note") or "").strip()
    classification = review.get("classification")
    if not event_id:
        raise ValueError("event_id is required")
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(ALLOWED_DECISIONS)}")
    if decision == "RECLASSIFY" and classification not in ALLOWED_CLASSES:
        raise ValueError(f"classification must be one of {sorted(ALLOWED_CLASSES)}")
    if decision in {"REJECT", "RECLASSIFY"} and not note:
        raise ValueError("note is required for REJECT/RECLASSIFY")
    record = {
        "review_id": str(uuid.uuid4()),
        "event_id": event_id,
        "decision": decision,
        "classification": classification,
        "note": note,
        "reviewed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "reviewer_identity": None,
        "identity_warning": "Local review mode has no authentication; reviewer identity is not verified.",
        "approval_status": "CANDIDATE",
    }
    audit_path = Path(path) if path else default_audit_path()
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


def read_reviews(path: str | Path | None = None) -> list[dict[str, Any]]:
    audit_path = Path(path) if path else default_audit_path()
    if not audit_path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(audit_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid audit JSON on line {line_number}") from exc
    return records
