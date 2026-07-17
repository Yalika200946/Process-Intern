"""Moved to src/models/phm_config.py — shim kept for the production
notebooks'/pipeline scripts' existing `sys.path.append(NB); import
phm_config` cells (see docs/MIGRATION_MAP.md). New code should import
`src.models.phm_config` directly."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.models.phm_config import *  # noqa: F401,F403
