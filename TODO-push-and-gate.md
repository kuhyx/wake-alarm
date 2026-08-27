# TODO — push the 31 local commits, and decide the 250-line gate

REMOVE ME AFTER FINISH

Everything from the phone-alarm session is **committed locally and verified on
hardware**. Nothing is at risk of being lost. The only thing left is getting it
to `origin/main`, which is blocked by a pre-existing gate failure this work did
not cause.

## The situation, precisely

`git push` runs a `ci-mirror` pre-push hook that runs `pre-commit --all-files`.
It fails on the **file-length <= 250** hook, for **seven Python files that were
already over the limit before this session started**:

```
wake_alarm/_sync.py             371
wake_alarm/_sinks.py            341
wake_alarm/_alarm_view.py       329
wake_alarm/_escape_flow.py      317
wake_alarm/tests/test_smart_plug.py  351
wake_alarm/tests/test_state.py       314
wake_alarm/tests/test_sync.py   (now split and under — see below)
```

Verified pre-existing: the identical set fails at `0e8da72`, the commit before
this session's work. **Every file this session touched is under 250** — where a
change pushed one over (`AGENTS.md`, `home_screen.dart`, `test_sync.py`,
`test_trigger.py`), it was split in the same change.

`--no-verify` is banned by `memories/git-rules.md`. Splitting untouched files is
banned by the standing rule in `TODO-hardening-continue.md` ("Do not split a
file the current change does not already have to touch") — that exact cascade
cost a full revert in an earlier session.

So this needs a human decision, which is why it is a TODO and not a fix.

## The prompt

```
In ~/wake-alarm there are 31 local commits that are not pushed. The pre-push
ci-mirror hook fails on the 250-line file-length gate, for seven Python files
that were ALREADY over the limit before this work started (verified: the same
set fails at 0e8da72). Nothing this session touched is over the limit.

Read TODO-push-and-gate.md first, then TODO-hardening-continue.md.

Pick ONE of these with me before doing anything:

A. Push with `git push --no-verify`, once, and say so in the session log.
   Fastest. Violates memories/git-rules.md, so it needs my explicit say-so
   (I have already given it once; re-confirm).

B. Split the seven pre-existing files properly, in their own commit, then
   push cleanly. This is real work — _sync.py in particular is the one item 8
   has to touch anyway, so doing it now front-loads that phase. Follow the
   traps in TODO-hardening-continue.md: splitting a test file loses its
   fixtures, moving a symbol silently breaks patch() targets, ruff's autofix
   strips imports and can gut a function whose result is only printed. After
   ANY split: /usr/bin/python3 -m pytest wake_alarm/tests/ -q must still be
   469 passed at 100% coverage, and `python -m wake_alarm._sync --show` and
   `python -m wake_alarm._trigger --dry-run` must still PRINT REAL OUTPUT
   (a CLI extracted to a new module has silently broken before).

C. Raise the gate's limit, or exempt the seven, and record why.

Do not split a file the change does not already have to touch. Do not
--no-verify without me choosing A.
```

## What is already done and verified (do not redo any of this)

Items **1, 4 and most of 3** from `TODO-hardening-continue.md` ship, and the
whole path is confirmed **on the Pixel 6a by the user**, not inferred:

- Fires from Doze on time; wakes the screen; `AlarmActivity` over the
  lockscreen; full-screen-intent notification posted.
- Rings under **priority** DND (`zen_mode=1`). Muted under **total silence**
  (`zen_mode=2`) — a real limit, documented in `DOCS-phone-alarm.md`.
- NFC tag registers and a tap dismisses; challenge solved; alarm silent.
- **Fully automatic**: arms itself with zero taps at 08:00 daily
  (`RTC_WAKEUP ... window=0`), no arm button, no cancel (the Kotlin handler is
  deleted, not just the Dart wrapper), earlier-only ratchet confirmed
  rejecting a later time on-device, one-shot reset after each fire, daily
  `AlarmWatchdog` plus a PC-side `_clamp_to_baseline()` watchdog.

Tests at HEAD: **469 Python at 100% branch coverage, 79 Dart**, `dart analyze`
clean. `FALLBACK_ALARM_HOUR` is now 8, matching the phone's baseline.

## Still genuinely open (not blockers for the push)

1. **QR scanner UI** — the only missing piece of item 3. `checkQr`,
   `RoomProofSettings` and the registration field all exist and are tested;
   `mobile_scanner` and a scan screen are what is missing.
2. **Locked-keyguard dismiss** — implemented (`requestDismissKeyguard`) but
   never run to completion. Note it raises the PIN prompt rather than silently
   unlocking, so a no-touch NFC tap is impossible on a secured phone.
3. **Item 8, mutual gating** — the next phase. It has to touch `_sync.py`, so
   option B above overlaps with it.
