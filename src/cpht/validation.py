"""
Data-validation helpers shared across `notebooks_v2/`.

Every notebook that reads a new artifact calls one of these before doing any
calculation on it -- this is the "validate at the boundary" gap flagged in
`docs/03_Business_Problem_and_Requirements.md` SS2.2 (the legacy pipeline's
`/api/run-full` path skips this; `/api/run` does it correctly). The new
pipeline does it every time, not just on one entry point.
"""
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    ok: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def raise_if_failed(self):
        if not self.ok:
            raise ValueError(
                "Data validation failed:\n  - " + "\n  - ".join(self.errors)
            )

    def report(self):
        status = "PASS" if self.ok else "FAIL"
        lines = [f"Validation: {status}"]
        for e in self.errors:
            lines.append(f"  [ERROR] {e}")
        for w in self.warnings:
            lines.append(f"  [WARN]  {w}")
        return "\n".join(lines)


def check_required_tags(available_tags, required_tags):
    """Every required tag must be present in the uploaded/loaded data."""
    available = set(available_tags)
    missing = sorted(set(required_tags) - available)
    result = ValidationResult(ok=len(missing) == 0)
    if missing:
        result.errors.append(f"{len(missing)} required tag(s) missing: {missing}")
    return result


def check_timestamp_column(df, timestamp_col="Timestamp"):
    result = ValidationResult(ok=True)
    if timestamp_col not in df.columns and df.index.name != timestamp_col:
        result.ok = False
        result.errors.append(f"'{timestamp_col}' column/index not found")
        return result
    ts = df[timestamp_col] if timestamp_col in df.columns else df.index
    n_na = ts.isna().sum() if hasattr(ts, "isna") else 0
    if n_na:
        result.warnings.append(f"{n_na} row(s) have an unparseable/missing timestamp")
    if len(ts) and hasattr(ts, "is_monotonic_increasing") and not ts.is_monotonic_increasing:
        result.warnings.append("timestamps are not monotonically increasing -- check for duplicate/out-of-order rows")
    return result


def check_value_ranges(df, tag, valid_min=None, valid_max=None):
    """Flag (not drop) values outside a physically plausible range for one tag."""
    result = ValidationResult(ok=True)
    if tag not in df.columns:
        result.ok = False
        result.errors.append(f"tag '{tag}' not in dataframe")
        return result
    s = df[tag]
    if valid_min is not None:
        n_low = (s < valid_min).sum()
        if n_low:
            result.warnings.append(f"{tag}: {n_low} value(s) below valid_min={valid_min}")
    if valid_max is not None:
        n_high = (s > valid_max).sum()
        if n_high:
            result.warnings.append(f"{tag}: {n_high} value(s) above valid_max={valid_max}")
    return result


def combine(*results):
    """Merge several ValidationResults into one (fails if any failed)."""
    ok = all(r.ok for r in results)
    errors = [e for r in results for e in r.errors]
    warnings = [w for r in results for w in r.warnings]
    return ValidationResult(ok=ok, errors=errors, warnings=warnings)
