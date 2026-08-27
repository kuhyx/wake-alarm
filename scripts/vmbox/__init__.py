"""Guest-side checks for the vmbox harness.

Not an importable part of ``wake_alarm`` -- these run *inside* a disposable
Arch guest, invoked by ``guest_cases.sh``. The package marker exists so they
are linted and type-checked like the rest of the repo instead of drifting as
loose scripts.
"""
