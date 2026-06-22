#!/usr/bin/env python3
"""Pre-commit hook: fail if any file exceeds MAX_LINES lines."""

from pathlib import Path
import sys

MAX_LINES = 500


def main() -> int:
    """Return 1 if any file exceeds the line limit, else 0."""
    failed = False
    for filepath in sys.argv[1:]:
        try:
            with Path(filepath).open(encoding="utf-8", errors="replace") as fh:
                count = sum(1 for _ in fh)
        except OSError:
            failed = True
            continue
        if count > MAX_LINES:
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
