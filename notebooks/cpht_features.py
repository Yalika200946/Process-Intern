"""Moved to src/features/heat_duty.py — shim kept for the production notebooks'
existing `sys.path.append(NB); from cpht_features import ...` (or
`import cpht_features`) cells (see docs/MIGRATION_MAP.md). New code should
import `src.features.heat_duty` directly."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.features.heat_duty import *  # noqa: F401,F403
