"""The ``--<act> | --dry-run | --show`` command line the v2 jobs share.

``_fallback`` (``--tick``) and ``_rtc`` (``--arm``) take the same three
modes, plus ``--at`` so a dry run can be asked "what would happen at 07:05
on Tuesday" without waiting for it -- the only way to check a morning-only
decision on the host in the afternoon.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def mode_parser(description: str, act: str, act_help: str) -> argparse.ArgumentParser:
    """A parser with exactly one of ``--<act>``, ``--dry-run``, ``--show``."""
    parser = argparse.ArgumentParser(description=description)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(f"--{act}", action="store_true", help=act_help)
    mode.add_argument("--dry-run", action="store_true", help="decide, change nothing")
    mode.add_argument("--show", action="store_true", help="current state")
    parser.add_argument(
        "--at",
        type=datetime.fromisoformat,
        help="with --dry-run: decide as of this local instant",
    )
    return parser


def parse_with_now(
    parser: argparse.ArgumentParser,
    argv: list[str] | None,
    now: Callable[[], datetime],
) -> tuple[argparse.Namespace, datetime]:
    """Parse ``argv`` (default ``sys.argv``) and resolve the instant to use."""
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.at is not None and not args.dry_run:
        parser.error("--at only goes with --dry-run")
    return args, now() if args.at is None else args.at.astimezone()
