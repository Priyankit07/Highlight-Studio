"""
Highlight Generator API package.
"""
import sys
from pathlib import Path

# Ensure codebase/ is on sys.path for flat imports
codebase_path = str(Path(__file__).resolve().parent.parent / "codebase")
if codebase_path not in sys.path:
    sys.path.insert(0, codebase_path)
