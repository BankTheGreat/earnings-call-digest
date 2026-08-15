"""Test bootstrap: repo root (for `import earnings_digest`) and tests/ (for
`import golden_input`) on sys.path, regardless of pytest's import mode."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _p in (_ROOT, _ROOT / "tests"):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)
