#!/usr/bin/env python3
"""Export what the emulator phone published to the Firebase RTDB emulator.

The emulator live checks (a ``bypass`` reaching "the test backend") use a
probe build that syncs to the PC's RTDB emulator instead of prod
(``phone_app/lib/services/sync_emulator.dart``). This reads it back exactly
the way the PC reads prod -- ``_sync_transport._read_published``: device
discovery plus the E2E unlock -- and writes the ``[[device_id, alarm], ...]``
list that ``python -m wake_alarm._fallback --dry-run --published`` takes.

Run it with ``HOME`` set to a scratch directory whose
``.config/crdt-sync/password`` holds the dummy test passphrase the AVD was
given, so the real passphrase is never read, and with
``PYTHONUSERBASE=/home/kuhy/.local`` so ``crdt_sync`` still imports::

    HOME=$SCRATCH PYTHONUSERBASE=$HOME/.local \\
        /usr/bin/python3 scripts/emu_published.py http://127.0.0.1:9000 out.json

``crdt_sync`` is imported unguarded on purpose: the transport degrades a
missing module to "nothing published", which here would read as a failed
check instead of a broken setup.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from crdt_sync import FirebaseSyncClient

from wake_alarm._sync_transport import _read_published


class _OwnerToken:
    """The emulator's admin token; the RTDB emulator accepts ``auth=owner``."""

    def id_token(self) -> str:
        """Every request's ``auth`` parameter."""
        return "owner"


def main(argv: list[str] | None = None) -> int:
    """Write the emulator's published logs to the output file; 1 when empty."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="the RTDB emulator's origin")
    parser.add_argument("out", type=Path, help="where to write the JSON list")
    args = parser.parse_args(argv)
    client = FirebaseSyncClient(args.url, _OwnerToken())  # type: ignore[arg-type]
    published = _read_published(client)
    pairs = [[device, json.loads(raw)] for device, raw in published]
    args.out.write_text(json.dumps(pairs, indent=1), encoding="utf-8")
    print(f"{len(pairs)} device(s): {' '.join(device for device, _ in pairs)}")
    return 0 if pairs else 1


if __name__ == "__main__":
    sys.exit(main())
