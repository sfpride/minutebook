#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""
scripts/import_minutes.py

Entry point alias for scripts/minutebook.py.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from minutebook import main

if __name__ == "__main__":
    main()
