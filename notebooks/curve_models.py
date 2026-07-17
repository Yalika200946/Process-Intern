"""Moved to src/models/fouling_curves.py — shim kept for the production
notebooks' existing `sys.path.append(NB); from curve_models import ...` (or
`import curve_models`) cells (see docs/MIGRATION_MAP.md). New code should
import `src.models.fouling_curves` directly."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.models.fouling_curves import *  # noqa: F401,F403
