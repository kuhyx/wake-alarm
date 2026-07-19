# wake_alarm

A phone-driven wake alarm for an always-on PC. The alarm time is whatever the
companion phone app last synced (via the shared `crdt_sync` transport over a
private GitHub repo); a per-minute systemd user timer fires at exactly that
time, showing a fullscreen, challenge-dismissed alarm with fan ramp and
optional TP-Link Tapo P110 smart-plug control.

Change the alarm on the phone at any hour and the PC follows within ~5
minutes. If the PC does happen to be powered down, a `shutdown` wrapper
hibernates with `rtcwake` set to the same synced time, as a fallback.

## Install

```bash
bash install.sh
```

This installs the package + dependencies into system Python's user
site-packages (the systemd units run `/usr/bin/python` directly, not a venv —
see `CLAUDE.md`), installs and enables the per-minute trigger timer, the
systemd-sleep resume hook, the `shutdown` wrapper that hibernates with
`rtcwake` as a fallback, the fan-ramp script, and (optionally) `python-kasa`
for smart-plug control.

Reading the phone's alarm needs a GitHub token with `repo` scope, at
`~/.config/wake_alarm/sync.json` as `{"token": "..."}`. If that file is
absent, a sibling app's `~/.config/{diet_guard,screen_locker}/sync_token` is
used instead, so one token covers every app syncing through `kuhyx/syncs`.

## Usage

```bash
python -m wake_alarm._alarm --demo     # test the alarm window (safe, closeable)
python -m wake_alarm._sync --show      # what alarm time the PC resolves
python -m wake_alarm._trigger --dry-run  # what the next tick would do
journalctl --user -fu wake-alarm-trigger.service  # watch it live
```

The alarm fires automatically once installed; no manual invocation is needed
in normal operation.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pre-commit install && .venv/bin/pre-commit install --hook-type pre-push
.venv/bin/python -m pytest wake_alarm/tests/ --cov=wake_alarm --cov-branch --cov-fail-under=100
```

See `CLAUDE.md` for scheduling details, the hibernate/`rtcwake` mechanism,
the cross-repo `workout_log.json` read, and production deployment gotchas.
