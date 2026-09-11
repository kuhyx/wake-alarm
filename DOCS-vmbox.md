# Testing wake_alarm in a disposable VM

`scripts/vmbox/harness.sh` is this repo's default gate for the shell and
system pieces — `install.sh`, the systemd units, `shutdown-wrapper.sh`, the
power-key inhibitor and the re-fire path. It provisions a throwaway Arch guest
(`~/src/utils/vmbox`), installs this repo into it exactly the way a real machine
does, runs the cases, and returns a host-side verdict.

```bash
bash scripts/vmbox/harness.sh              # the gate
bash scripts/vmbox/harness.sh --window     # also screenshot the real alarm window
bash scripts/vmbox/harness.sh --keep       # leave the sandbox up to poke at
```

Exit codes: `0` everything passed, `1` a case failed, `2` the harness itself
could not run.

## Why a VM at all

Every one of these touches something a test on the host cannot safely touch:
`install.sh` writes systemd user units, a sudoers entry and
`/usr/local/bin/shutdown`; the shutdown wrapper's whole job is to hibernate the
machine; the inhibitor takes a logind lock on the power button. Getting any of
those wrong on the host is not a failed test, it is a broken machine.

## What it actually covers

| Case | What a pass means |
|---|---|
| `imports-from-system-python` | `wake_alarm` and `gatelock` import under `/usr/bin/python3`, the interpreter the units really use — not a venv |
| `trigger-timer-enabled` | `wake-alarm-trigger.timer` is enabled after `install.sh`. Writing the unit file is not the same as systemd running it, and a timer that is present but disabled fails silently every morning |
| `trigger-dry-run` | one tick reaches a decision without crashing |

`install.sh` itself running to completion is a precondition of all of them: if
it fails, the harness stops with exit 2 and dumps the log.

## What it cannot cover — do not read a pass as covering these

- **The phone.** The entire dismiss sequence — two NFC tags, the step counter,
  the challenges, the 5-minute bypass — lives in `phone_app/` and is verified
  on the Pixel 6a, never here. This harness knows nothing about it.
- **The bootloader.** The guest is BIOS/GRUB, this PC is UEFI. Any
  firmware/ESP work goes straight to the host.
- **A green run is not host verification.** Report it as "passed in vmbox, not
  verified on the host", always.

## Guest provisioning, and why

The stock guest image is missing exactly one thing this package needs:

- **`tk`** — without it `import tkinter` fails with `libtk8.6.so: cannot open
  shared object file` and the alarm cannot open its window at all.

`gatelock` is not installed separately: it is a `pyproject.toml` dependency, so
`install.sh`'s `pip install -e` pulls it from its pinned tag. That is
deliberate — the harness runs the real install path rather than a hand-rolled
approximation, so a break in `install.sh` fails the gate.

## Two traps worth knowing before editing the harness

- **`vm run` does not propagate the guest command's exit code.** It reports the
  *VM's* verdict (clean / dirty / rebooted / crashed / hung), so a guest script
  exiting 1 still returns 0 on the host. A gate built on that exit code fails
  *open*, which is worse than no gate. `guest_cases.sh` therefore prints
  `ALL-CASES-PASSED` only when every case passed, and the harness greps for it.
- **`vm share` and `vm repo` key off the path's basename**, so the repo path
  must be absolute and symlink-resolved. A relative `scripts/vmbox/../..`
  makes rsync write into `/home` and fail with permission errors that look
  like a guest problem.

## Cases this VM found that the host could not (historical)

Both were live bugs, both passed the unit suite:

1. **The inhibitor claimed a block it did not have.** `Popen` succeeding only
   means the binary launched; logind can still refuse. The alarm logged "power
   key inhibited" while `systemd-inhibit` had already exited 1.
   `take_power_key_inhibitor()` now waits briefly and confirms the child
   survived.
2. **An unsigned session record was written and then rejected on read.** With
   no HMAC key on the machine (`/etc/gatelock` absent, as in the guest),
   `verify_entry_hmac` returns False, so every session record was unreadable
   and the power-off defence silently did not exist. An entry with *no* `hmac`
   field is now honoured with a loud warning, while a *present but wrong*
   signature is still rejected — that one really is tampering.
