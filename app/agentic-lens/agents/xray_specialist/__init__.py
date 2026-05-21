# Ensure agent folder is on sys.path so src.kb_tools and other local modules are importable.
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
