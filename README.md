# wake_alarm

**The phone is the alarm.** `phone_app/` arms and rings it, and getting past it
means walking between two NFC tags and answering three questions. This repo's
Python half no longer wakes anyone: all it does is read the alarm time the
phone published and start the morning routine (the workout lock) at that time.

## The dismiss sequence

Strict, ordered, and latched — every stage required, and a stage once passed
never reverts:

```
tag 1  ->  25 steps + 2 min  ->  tag 2  ->  3 challenges
```

The two tags must be *distinct* and live in different rooms; the same id in
both slots is refused at registration. Answers are cumulative, so a wrong one
costs the attempt and nothing else.

**One fallback, deliberately narrow.** After 5 minutes of ringing — or
immediately if NFC is off or fewer than two tags are registered — the two *tag*
stages are skipped and the challenge count rises to 6. The walk is never
skipped. Without a hatch of some kind, a dead tag at 06:00 leaves an alarm that
cannot be switched off at all.

Details, and the things that are a hard crash or a silent no-ring:
**`DOCS-phone-alarm.md`**.

## The PC half

A per-minute systemd user timer (`wake-alarm-trigger.timer`) reads the alarm
the phone published through the shared `crdt_sync` transport, and at that time
starts `morning-routine.service`, which runs the workout lock. It records a
once-per-day latch so the rest of the catch-up window does not restart it.

That is all it does. There is no alarm window, no audio, no smart plug, no
`rtcwake`, and no `shutdown` wrapper.

## Install

```bash
bash install.sh      # trigger timer
bash uninstall.sh    # removes it, and any retired waking machinery
```

`install.sh` installs the package into system Python's user site-packages (the
units run `/usr/bin/python` directly, not a venv — see `CLAUDE.md`) and enables
the timer. It also clears the retired pieces an older install left behind,
notably `/usr/local/bin/shutdown`, which is root-owned and would otherwise keep
turning `shutdown now` into a hibernate forever.

Reading the phone's alarm uses the shared `~/.config/crdt-sync/firebase.json`.
The GitHub mirror (fallback only) needs a `repo`-scoped token at
`~/.config/wake_alarm/sync.json` as `{"token": "..."}`.

## Usage

```bash
python -m wake_alarm._sync --show        # what alarm time the PC resolves
python -m wake_alarm._trigger --dry-run  # what the next tick would do
journalctl --user -fu wake-alarm-trigger.service  # watch it live
```

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pre-commit install && .venv/bin/pre-commit install --hook-type pre-push
.venv/bin/python -m pytest wake_alarm/tests/ --cov=wake_alarm --cov-branch --cov-fail-under=100
cd phone_app && flutter test && flutter analyze
```

The dev venv lacks `gatelock`, so anything importing `_state` (including
`_trigger`) needs `/usr/bin/python3`, not `.venv/bin/python`.

See `CLAUDE.md` for the sync resolution chain, the cross-repo coupling to
`morning_routine`, and production deployment gotchas.
