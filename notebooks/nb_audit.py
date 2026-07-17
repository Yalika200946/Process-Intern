"""Moved to src/validation/nb_audit.py — shim kept for the production
notebooks' existing `sys.path.append(NB); import nb_audit as A` cells (see
docs/MIGRATION_MAP.md). New code should import `src.validation.nb_audit`
directly."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.validation.nb_audit import *  # noqa: F401,F403
