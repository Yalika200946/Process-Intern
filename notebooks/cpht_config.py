"""Moved to src/domain/config.py — shim kept for the production notebooks'
existing `sys.path.append(NB); from cpht_config import ...` (or
`import cpht_config`) cells (see docs/MIGRATION_MAP.md). New code should
import `src.domain.config` directly."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.domain.config import *  # noqa: F401,F403
