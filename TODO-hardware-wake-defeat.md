# Hardware ideas: defeat a fully-powered-off phone

REMOVE ME AFTER FINISH

Both items below were scoped during the 2026-09-23 workday-stick session
(`DOCS-morning-session-pc.md`) and explicitly deferred out of scope for that
session: no existing firmware project and no owned wearable, both need a real
purchase before any code gets written. Written here instead of
`~/src/todo/BACKLOG.md` because that file is gitignored/export-only from the
todo app and a manual edit there is silently lost on the next export — this
is the durable copy.

## Item 1 — second wake-alarm device: rings independently of the phone's power state

### what
An ESP32 + buzzer that polls the same Firebase alarm/session record
wake-alarm already reads and keeps ringing until it sees a dismiss or a
started session — so powering the phone off can no longer silently kill the
whole wake attempt the way it does today.

### where
new repo (no existing ESP32/PlatformIO/Arduino project anywhere in `~/src`
to build on — checked). Firebase-only, per the "new syncing apps are
Firebase-only" rule.

### must
- must not require the phone to relay anything — the whole point is
  surviving the phone being off.
- optional: a physical snooze/dismiss button, since the phone's own dismiss
  gate isn't reachable from the device.

### done
On a Tue/Wed/Thu, power the phone off right at the alarm and the ESP32
still rings, and keeps ringing, until the phone's session shows a start.

### verify
Bench test first (USB power, no case), then a real overnight run.

### read first
- `DOCS-phone-alarm.md` (the Firebase alarm schema to poll)
- `DOCS-morning-session-pc.md` (why this exists: the workday-stick project,
  2026-09-23)

## Item 2 — wearable wake-defeat check

### what
A cheap fitness band whose own sleep log (stored on the band, synced later)
can show "asleep again after the alarm rang" even when the phone was fully
off and missed the whole thing.

### where
new app or an extension of `phone_app/`, once a device is picked.

### must
- must not: buy or integrate anything before checking Gadgetbridge's
  current supported-device list — research first, kuhy owns no wearable and
  none is integrated anywhere in `~/src` today (checked).

### done
Not yet scoped — picking a supported device is the blocking step.

### verify
Blank — desktop, once there's something to verify.
