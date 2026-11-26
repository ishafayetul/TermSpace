#!/usr/bin/python3 -I
"""Launch TermSpace from the source tree or the installed launcher symlink."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from termspace.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
