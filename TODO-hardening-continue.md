# Wake-alarm hardening — continue here

REMOVE ME AFTER FINISH

Phases 0–7 are committed (`4286fcb`..`f5eb7fc`). This file is the entry point
for the rest. **Full plan, with every measured finding:**
`~/.claude/plans/wake-alarm-still-does-witty-toucan.md` — read it before
starting; this file deliberately does not duplicate it.

## Done so far

| Item | State |
|---|---|
| 6 audio (HDMI silent) | **Done.** `_reactivate` wired into `WakeAlarm`; verified on the host — the HDMI sink appeared and became default. |
| 7 speakers | `DOCS-speaker-recommendation.md`. Prose only, done. |
| 9 refactor | `_alarm.py` 478→250. 12 new modules; see `DOCS-architecture.md`. |
| 11 failsafe | `FAILSAFE_SILENCE_SECONDS=300`, audio only. Escalation re-tuned to fit inside it. |
| 12 logging | JSONL + cross-process dedupe + derived correlation id. |
| 14 fans | Gone: code, script, sudoers entry, installed state. Three stale doc/message references cleaned up in phase 6. |
| 2 power button | **Done.** `_inhibit.py` (logind block, self-terminating, stale cleanup by pid via `/proc`) + `_alarm_session.py` fire-time record, re-fired by `_trigger` outside the catch-up window. |
| 10 vmbox | **Done.** `scripts/vmbox/harness.sh` + `DOCS-vmbox.md`. 8 cases, fails closed. Found 2 live bugs the host could not reach. |
| 5 curtains | **Done.** `_curtains.py` driver protocol + no-op default, called from `prepare_hardware()`. `DOCS-curtains-hardware.md` has the buy list. |
| 1/4 phone alarm | **Done.** Five Kotlin files behind one MethodChannel + the Dart ring screen. The phone arms and rings its own alarm; no Clock-app confirmation. Verified on the API 36 AVD (screen Asleep→Awake, AlarmActivity over the lockscreen) and deployed to the Pixel 6a. |
| 3 room proofs | **Mostly done.** NFC (hand-written `NfcReader.kt`) and the steps+elapsed fallback ship and are wired into the ring screen. QR is specified and unit-tested (`checkQr`) but has **no scanner UI** — `mobile_scanner` was left as the droppable extra. |

## Remaining, in order

1. **Item 3 leftovers.** The QR scanner UI (`mobile_scanner`) and a Settings
   screen to register the NFC tag id / QR payload. `RoomProofSettings` already
   persists both and `RoomProof.checkQr` is unit-tested — what is missing is
   only the UI that feeds them. NFC and the steps fallback already work, so
   the alarm is dismissable without this.
2. **Item 8, mutual gating.** Phone half is now in place. This is the phase
   that legitimately touches `_sync.py`, so it carries that split (see below).
3. **Item 13, black screen.** Different repo (`~/testsAndMisc/
   linux_configuration`), host-only, blocks nothing.

### Not yet verified on the phone

The ring itself has only been fired on the API 36 AVD. On the Pixel 6a the
build installs and the runtime permission prompts appear, but **an actual
alarm has never rung on it** — that needs an alarm armed through the picker
(which needs a sync backend connected) and a wait to the fire instant. Ring
with **DND on**, since "STREAM_ALARM ignores DND" is the load-bearing claim
and has not been observed on hardware.

## Decisions already made — do not re-litigate

- Failsafe stops **sound only**; lock, challenge and workout gate persist.
- Gating is **phone first, then PC**, with a bounded escape: if sync is
  unreachable for ~600 s the PC gate degrades to locally-solvable, logged
  WARNING. Without that, a Firebase outage means you can neither dismiss nor
  get to work.
- Room proof: NFC **or** QR qualifies. **Steps alone does not** — the phone is
  stationary in the other room while you walk *to* it, so steps only accrue
  after pickup and can be faked by shaking it in bed. Steps + elapsed time is
  the fallback when both others fail. (I narrowed "any one satisfies" here;
  say if you disagree.)
- Phone alarm: hand-written Kotlin behind one MethodChannel, **not** a plugin.
  AGP 9.0.1 / Gradle 9.1 / Kotlin 2.3.20 is bleeding edge and a plugin that
  won't compile breaks the build outright. `STREAM_ALARM` is load-bearing —
  it is what ignores DND and silent mode.
- Curtains: no hardware; pluggable driver + logging no-op default.
- Quality bar: 100% branch coverage, no new `# noqa` / `type: ignore`.

## Traps found in the phone session

- **The plan's `LogStore.changes` does not exist.** `crdt_sync_dart` has no
  Stream at all. Re-arm therefore needs three explicit hooks — startup,
  BOOT_COMPLETED, dismiss — and dropping any one makes the alarm ring once
  and then silently stop forever.
- **The Android SDK was never missing, only unexported.** `~/Android/Sdk` has
  `cmdline-tools`, `emulator` and `platform-tools`; only `adb` was on PATH.
  Export `ANDROID_HOME` rather than installing anything.
- **A permission declared in the manifest is not a permission granted.**
  Both `POST_NOTIFICATIONS` and `ACTIVITY_RECOGNITION` are runtime grants, and
  each one missing silently breaks a different half of the dismiss path
  (no full-screen intent / no step sensor). The AVD caught both because a
  freshly installed app there sits at `importance=NONE`.
- **A debug probe entrypoint with its own UI proves nothing about the route.**
  The first probe rendered its own widget, so the AVD run validated the Kotlin
  and nothing about `/ring`. Point the probe at the real app widget.

## Traps that cost time this session

- **The 250-line gate fires on *staged* files.** Touching a file means
  splitting it in the same commit. Still over (re-measured 2026-08-27, after
  phase 6): `test_sync.py` 386, `_sync.py` 371, `test_smart_plug.py` 351,
  `_sinks.py` 341, `_alarm_view.py` 329, `_escape_flow.py` 317,
  `test_state.py` 314. Budget for it. `test_trigger.py` is now split and
  under.
- **`morning_routine/_orchestrator.py:39` hardcodes `"wake_alarm._alarm"`**
  (different repo, `~/testsAndMisc`). Any module-path change updates it in the
  *same* commit. This exact omission caused a month-long silent outage. Keep
  `main()` in `_alarm.py`.
- **Splitting a test file loses its fixtures.** `_make_mock_tk`,
  `_block_real_tk` and `_block_extra_devices` live *after* the imports, so a
  naive header-copy drops them and every test errors. Copy the whole region
  before the first `class`. Also: a multi-line module docstring gets stranded
  if you replace only its first line.
- **Moving a symbol breaks `patch("wake_alarm._alarm.X")` silently** — the
  patch stops intercepting and the test asserts nothing. Grep the whole
  `tests/` tree for the old target after any move.
- **Autoformat strips an import added before its first usage.** `struct`
  vanished from the extracted `_tone.py`; ruff, mypy and pylint all passed.
  Only running it caught the `NameError`. Add import and usage in one edit.
- **Never let a beep-loop test miss its rung.** A test that patches only one
  of `_beep_soft/_medium/_loud` and waits for it will spin forever on the real
  audio stack and hang the whole suite instead of failing. Patch all three.
- Run tests with `/usr/bin/python3`, not the dev venv (no `gatelock` there).
- **`vm run` does not propagate the guest command's exit code** — it reports
  the VM's verdict. A gate built on it fails *open*. See `DOCS-vmbox.md`.
- **`_state.py`'s UTC `_today_str()` must NOT be flipped to local**, despite
  what the plan says. `screen_locker/_wake_state.py` mirrors the helper and
  reads the same `wake_state.json`; flipping it loses an earned workout skip
  for any dismissal between 00:00 and 02:00 local. `_alarm_session.py` shows
  the way around it: carry an aware `fired_at`, compare elapsed time, no date
  key at all.
- **Do not split a file the current change does not already have to touch.**
  The gate fires on *staged* files, so an oversized file only becomes your
  problem once you edit it. Editing `_sync.py` merely to repoint an import
  pulled its 371 lines into the changeset and cascaded into five new modules
  and a broken tree before being reverted. Prefer putting a new constant in
  its single consumer (as `_curtains.py` does) over touching `_constants.py`.
- **A `__main__` CLI extracted to a new module breaks its documented command
  silently.** `python -m wake_alarm._sync --show` printed nothing and exited
  0 — invisible to ruff, mypy, pylint and the suite alike. If a later phase
  moves that CLI, run the documented command and check the *output*.
- **Ruff's autofix will gut a function** whose results are only printed —
  it stripped both the assignments and the `print` from a vmbox check, and
  every linter stayed green. Grep the file for its output call after any
  autofix.

## Verify

```
/usr/bin/python3 -m pytest wake_alarm/tests/ -q          # 455 pass, 100% cov
bash scripts/vmbox/harness.sh                           # 8/8 cases, exit 0
pre-commit run --files <changed>
/usr/bin/python3 -m wake_alarm._trigger --dry-run
/usr/bin/python3 -m wake_alarm._alarm --demo             # real window; ask first
```

Done = every item above shipped, this file deleted.
