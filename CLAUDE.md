# CLAUDE.md — wake_alarm

## What this does

A weekend wake alarm: on alarm days (`ALARM_DAYS` in `_constants.py` — Mon,
Fri, Sat, Sun), the machine hibernates overnight and wakes itself via
`rtcwake` at the configured alarm time. `wake-alarm.service` then opens a
fullscreen Tk window that must be dismissed (with a typed challenge — see
`_challenges.py`), ramps fans to 100% via `wake-alarm-fans.sh`, plays audio
through whatever sink comes up after the monitor wakes, and optionally
toggles a TP-Link Tapo P110 smart plug via `python-kasa`.

## Scheduling — hibernate-based, not a systemd timer

There is **no systemd timer** for this package. The wake mechanism is:

1. `shutdown-wrapper.sh`, installed to `/usr/local/bin/shutdown` (shadowing
   `/usr/bin/shutdown` via PATH order), intercepts shutdown/poweroff calls on
   alarm nights and calls `rtcwake -m disk` instead — hibernating with the
   RTC alarm set to wake the machine at `WAKE_AFTER_HOURS` (`_constants.py`)
   from now.
2. `sleep-hook.sh`, installed to `/usr/lib/systemd/system-sleep/`, fires on
   resume (`$1 == post`) and starts `morning-routine.service` for every
   logged-in session. That orchestrator (lives in testsAndMisc, not here —
   see below) runs the alarm first, then the workout screen lock, so the two
   never fight for the fullscreen.
3. `wake-alarm.service` itself is `Type=simple`, started either directly or
   by the orchestrator, and exits once the alarm is dismissed.

If you change `WAKE_AFTER_HOURS` in `_constants.py`, you must also update the
duplicate constant in `shutdown-wrapper.sh` (`WAKE_AFTER_HOURS=8`) — they are
not wired together, by design (the shell wrapper has no Python runtime
available at the point it intercepts `shutdown`).

## Cross-repo coupling — not a bug

`_constants.py`'s `WORKOUT_LOG_FILE` points at
`~/screen-locker/screen_locker/workout_log.json` — a file owned by the
separate, already-standalone `screen-locker` repo
(https://github.com/kuhyx/screen-locker). This is intentional: the alarm
reads whether today's workout was already logged by screen-locker to decide
whether the morning routine should also lock the workout screen. If this
path ever raises `ModuleNotFoundError`-style confusion, the bug is almost
certainly in the **orchestrator** (`morning_routine` in testsAndMisc), not
here — see the next section.

## The morning_routine orchestrator lives elsewhere

`morning_routine._orchestrator` (in `testsAndMisc/python_pkg/morning_routine/`)
runs this package and `screen_locker` as two sequential subprocesses. When
either package is extracted to its own repo, **the orchestrator's module
reference must be updated in the same change** — this exact mistake
(orchestrator left pointing at `python_pkg.screen_locker.screen_lock` after
screen-locker's extraction on 2026-05-28) caused a month-long silent
production failure where the alarm fired and dismissed correctly but the
workout lock crashed with `ModuleNotFoundError` on every run. Once both
`wake_alarm` and `screen_locker` are pip-installed system-wide, the
orchestrator needs no `PYTHONPATH`/`cwd` plumbing — plain
`subprocess.run([sys.executable, "-m", module, "--production"])` resolves
both.

## Production dependency installation — read this before adding any dependency

`wake-alarm.service` runs `/usr/bin/python` directly — **not** a venv. Any
new non-stdlib dependency (this package itself, `gatelock`, `python-kasa`,
anything added later) must be installed into system Python's *user*
site-packages:

```bash
/usr/bin/python3 -m pip install --user --break-system-packages -e .
```

`install.sh` already does this. **If you add a dependency and only install it
into a dev venv, the production service will silently fail with
`ModuleNotFoundError` on its next run** — this exact gap caused a 3-day
diet_guard production outage (2026-06-19 to 2026-06-22) for the sibling
`gatelock` migration. Always verify against
`/usr/bin/python3 -c "import <new_dep>"`, not just the dev venv, before
considering a dependency change done.

## Operational gotchas

- **`python-kasa` is optional at runtime** (`_smart_plug.py` catches
  `ImportError` and disables smart-plug control with a warning log), but it
  *is* a hard dependency for this repo's own tooling (mypy/pylint/tests need
  it importable) — see `pyproject.toml`/`requirements.txt`.
- **The `wave` module needs special pylint handling.** `_audio.py` opens WAV
  files in write mode; pylint's stdlib stub infers the read-mode overload and
  wrongly flags `setnchannels`/`setsampwidth`/`setframerate`/`writeframes` as
  missing. See the `generated-members` list in `pyproject.toml`'s
  `[tool.pylint.typecheck]` — don't remove it if pylint starts complaining
  about `wave.Wave_write`.
- **`wake_state.json` is runtime state, not tracked.** It holds the
  HMAC-signed dismissal record for the current alarm day. It used to be
  accidentally committed in the monorepo; it is gitignored here and must
  stay that way.

## Commands

- Run tests: `python -m pytest wake_alarm/tests/ --cov=wake_alarm --cov-branch --cov-fail-under=100`
- Lint: `pre-commit run --all-files`
- Test the lock manually (safe, closeable): `python -m wake_alarm._alarm --demo`
- Install for production: `bash install.sh`

## Do NOT

- Don't add a dependency without doing the production install-path check
  above.
- Don't forget the orchestrator when changing this package's module path or
  invocation — see "The morning_routine orchestrator lives elsewhere" above.
- Don't commit `wake_state.json`.
