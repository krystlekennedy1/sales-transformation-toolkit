"""The diagnostic reuses the ramp coach, which lives in the sibling ramp-coach folder."""
import sys
from pathlib import Path

_RAMP = Path(__file__).resolve().parents[2] / "ramp-coach"
if str(_RAMP) not in sys.path:
    sys.path.insert(0, str(_RAMP))
