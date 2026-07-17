"""Moved to src/features/crude_properties.py — shim kept for the production
notebooks' existing `sys.path.append(NB); from crude_properties import ...`
(or `import crude_properties`) cells (see docs/MIGRATION_MAP.md). New code
should import `src.features.crude_properties` directly."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.features.crude_properties import *  # noqa: F401,F403
