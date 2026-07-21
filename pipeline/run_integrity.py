"""Run manifests, validation, and immutable dashboard snapshot publication."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.governance import approval_summary, config_hash, utc_now


ROOT = Path(__file__).resolve().parents[1]
DASH_DATA = ROOT / "dashboard" / "data"
SNAPSHOTS = ROOT / "dashboard" / "snapshots"
RUNS = ROOT / "reports" / "runs"
POINTER = DASH_DATA / "current_snapshot.json"
SCHEMA_VERSION = "review-1.0"
EXCLUDE = {
    "current_snapshot.json", "cost_overrides.json", "cit_floor_override.json",
    "furnace_limit_overrides.json", "opt_params.json",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True, timeout=10, check=False,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _data_as_of(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("data_as_of", "last_timestamp", "as_of", "generated_at"):
            if payload.get(key) is not None:
                return str(payload[key])
    return None


def _decorate(payload: Any, generation_id: str, generated_at: str) -> Any:
    meta = {
        "generation_id": generation_id,
        "generated_at": generated_at,
        "data_as_of": _data_as_of(payload),
        "schema_version": SCHEMA_VERSION,
        "approval_summary": approval_summary(),
    }
    if isinstance(payload, dict):
        decorated = dict(payload)
        decorated["_meta"] = meta
        decorated.setdefault("approval_summary", meta["approval_summary"])
        decorated.setdefault("assumption_flags", meta["approval_summary"]["assumption_flags"])
        return decorated
    return {"data": payload, "_meta": meta, "approval_summary": meta["approval_summary"]}


def collect_validation_errors(snapshot_dir: Path) -> list[str]:
    errors: list[str] = []
    required = {
        "pfd_topology.json", "engineering_priority.json", "model_metrics.json",
        "forecast_6mo.json", "cleaning_plan.json", "evidence.json",
    }
    missing = sorted(name for name in required if not (snapshot_dir / name).is_file())
    if missing:
        errors.append(f"Missing required dashboard artifacts: {missing}")
    generation_ids: set[str] = set()
    for path in snapshot_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"Invalid JSON {path.name}: {exc}")
            continue
        meta = payload.get("_meta") if isinstance(payload, dict) else None
        if not isinstance(meta, dict):
            errors.append(f"Missing _meta in {path.name}")
        elif meta.get("generation_id"):
            generation_ids.add(str(meta["generation_id"]))
        else:
            errors.append(f"Missing generation_id in {path.name}")
    if len(generation_ids) > 1:
        errors.append(f"Mixed generation IDs: {sorted(generation_ids)}")
    return errors


def publish_snapshot(
    generation_id: str,
    *,
    input_path: Path | None,
    step_results: list[dict[str, Any]],
    started_at: str,
) -> dict[str, Any]:
    """Copy live outputs into an immutable snapshot and atomically move its pointer."""
    generated_at = utc_now()
    snapshot_dir = SNAPSHOTS / generation_id
    if snapshot_dir.exists():
        raise RuntimeError(f"Snapshot already exists: {snapshot_dir}")
    snapshot_dir.mkdir(parents=True)

    artifacts: list[dict[str, Any]] = []
    for source in sorted(DASH_DATA.glob("*.json")):
        if source.name in EXCLUDE:
            continue
        payload = json.loads(source.read_text(encoding="utf-8"))
        destination = snapshot_dir / source.name
        destination.write_text(
            json.dumps(_decorate(payload, generation_id, generated_at), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        artifacts.append({
            "name": source.name,
            "sha256": sha256_file(destination),
            "bytes": destination.stat().st_size,
            "schema_version": SCHEMA_VERSION,
        })

    errors = collect_validation_errors(snapshot_dir)
    manifest = {
        "schema_version": "1.0.0",
        "generation_id": generation_id,
        "mode": "REVIEW",
        "started_at": started_at,
        "finished_at": generated_at,
        "input": ({"path": str(input_path), "sha256": sha256_file(input_path)}
                  if input_path and input_path.is_file() else None),
        "config_hash": config_hash(),
        "code_revision": git_revision(),
        "environment": {"python": sys.version, "platform": platform.platform()},
        "steps": step_results,
        "artifacts": artifacts,
        "approval_summary": approval_summary(),
        "validation": {"passed": not errors, "errors": errors},
    }
    (snapshot_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    run_dir = RUNS / generation_id
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(snapshot_dir / "run_manifest.json", run_dir / "run_manifest.json")
    if errors:
        raise RuntimeError("Publish validation failed: " + "; ".join(errors))

    pointer_payload = {
        "generation_id": generation_id,
        "snapshot": str(snapshot_dir.relative_to(ROOT / "dashboard")).replace("\\", "/"),
        "published_at": generated_at,
        "manifest": "run_manifest.json",
    }
    temporary = POINTER.with_suffix(".tmp")
    temporary.write_text(json.dumps(pointer_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, POINTER)
    return manifest


def resolve_published_artifact(name: str) -> Path | None:
    if not POINTER.is_file():
        return None
    pointer = json.loads(POINTER.read_text(encoding="utf-8"))
    snapshot = ROOT / "dashboard" / pointer["snapshot"]
    candidate = (snapshot / Path(name).name).resolve()
    if snapshot.resolve() not in candidate.parents or not candidate.is_file():
        return None
    return candidate
