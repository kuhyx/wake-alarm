# Wake-alarm hardening — continue here

REMOVE ME AFTER FINISH

Phases 0–3b are committed (`4286fcb`..`b3e8c23`). This file is the entry point
for the rest. **Full plan, with every measured finding:**
`~/.claude/plans/wake-alarm-still-does-witty-toucan.md` — read it before
starting; this file deliberately does not duplicate it.

## Done so far

| Item | State |
|---|---|
| 6 audio (HDMI silent) | `_reactivate.py` retries card-profile activation. **Not yet wired into `WakeAlarm`** — see below. |
| 7 speakers | `DOCS-speaker-recommendation.md`. Prose only, done. |
| 9 refactor | `_alarm.py` 478→250. 12 new modules; see `DOCS-architecture.md`. |
| 11 failsafe | `FAILSAFE_SILENCE_SECONDS=300`, audio only. Escalation re-tuned to fit inside it. |
| 12 logging | JSONL + cross-process dedupe + derived correlation id. |
| 14 fans | Gone: code, script, sudoers entry, installed state. |

## Remaining, in order

1. **Wire `_reactivate` into `WakeAlarm`** (finishes item 6). It exists,
   is tested, and is currently called by nothing. Start it next to
   `_activate_all_outputs()` in `__init__`, pass `self._stop_beep` as `stop`.
   ~20 lines. Do this first — every other item assumes the alarm is audible.
2. **Item 2, power button.** `systemd-inhibit
   --what=handle-power-key:shutdown:idle --mode=block` around the alarm, in a
   new `_inhibit.py`, released in `on_close()`. Verified viable:
   `PowerKeyIgnoreInhibited=no` is in force, so no `logind.conf` edit is
   needed. Then the real defence — a **fire-time** session record
   (`wake_state.json` is only written on *dismissal* today, so a hard
   power-off leaves no trace), and `_trigger` re-fires on an unfinished
   session ignoring the catch-up window. Fix the UTC/local key mismatch in
   `_state.py` in the same commit.
3. **Item 10, vmbox harness.** `scripts/vmbox/harness.sh` + `DOCS-vmbox.md`.
4. **Items 4/3/1, phone.** Biggest chunk by far. Own session.
5. **Item 8, mutual gating.** Needs 4 done first.
6. **Item 5 curtains**, then **item 13 black screen** (different repo,
   host-only).

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

## Traps that cost time this session

- **The 250-line gate fires on *staged* files.** Touching a file means
  splitting it in the same commit. 5 source + several test files are still
  over (measured 2026-08-27): `test_sync.py` 386, `_sync.py` 371,
  `test_smart_plug.py` 351, `_sinks.py` 341, `_alarm_view.py` 329,
  `_escape_flow.py` 317, `test_state.py` 314, `test_trigger.py` 252.
  Budget for it.
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

## Verify

```
/usr/bin/python3 -m pytest wake_alarm/tests/ -q          # 404 pass, 100% cov
pre-commit run --files <changed>
/usr/bin/python3 -m wake_alarm._trigger --dry-run
/usr/bin/python3 -m wake_alarm._alarm --demo             # real window; ask first
```

Done = every item above shipped, this file deleted.
