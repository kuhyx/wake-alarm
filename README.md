# wake_alarm

A hibernate-scheduled weekend wake alarm: the machine hibernates overnight
on alarm days and wakes itself via `rtcwake`, then shows a fullscreen,
challenge-dismissed alarm with fan ramp and optional TP-Link Tapo P110
smart-plug control.

## Install

```bash
bash install.sh
```

This installs the package + dependencies into system Python's user
site-packages (the systemd service runs `/usr/bin/python` directly, not a
venv — see `CLAUDE.md`), installs the systemd user service, the
systemd-sleep resume hook, the `shutdown` wrapper that triggers hibernate on
alarm nights, the fan-ramp script, and (optionally) `python-kasa` for
smart-plug control.

## Usage

```bash
python -m wake_alarm._alarm --demo   # test the alarm window (safe, closeable)
```

The alarm fires automatically via the hibernate/wake cycle once installed;
no manual invocation is needed in normal operation.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pre-commit install && .venv/bin/pre-commit install --hook-type pre-push
.venv/bin/python -m pytest wake_alarm/tests/ --cov=wake_alarm --cov-branch --cov-fail-under=100
```

See `CLAUDE.md` for scheduling details, the hibernate/`rtcwake` mechanism,
the cross-repo `workout_log.json` read, and production deployment gotchas.
