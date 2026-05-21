# Ensure agent folder is on sys.path for legacy imports (peer agents use their own `src/` packages).
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
