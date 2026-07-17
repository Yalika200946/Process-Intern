"""
pytest config: put `notebooks/` and `pipeline/` on sys.path so tests can `import nb_audit`,
`import cleaning_scheduler_network`, etc. the same way the notebooks/pipeline scripts already
do (via their own sys.path.append(str(NB)) pattern) -- not a new import convention.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
for sub in ("notebooks", "pipeline"):
    p = str(REPO / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
