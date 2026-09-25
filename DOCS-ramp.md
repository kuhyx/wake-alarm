# The wake-time ramp ("cooking the frog")


The baseline is not a constant: 08:00 through 2026-09-25, then one minute
earlier per **calendar** day (free days count) to 07:00 on 2026-11-24, which
is permanent. A pure function of the date the alarm **fires** on — no counter,
no stored start — so a reinstall cannot reset it. Three copies must agree:
`wake_alarm/_ramp.py` (PC fallback + clamp), `phone_app/lib/services/alarm_ramp.dart`
(`AlarmPolicy`) and `AlarmRamp.kt` (every native arm path funnels through
`AlarmScheduler.nextOccurrence`, so the dismiss/boot/free-day/watchdog re-arms
keep stepping without Dart). `tests/test_ramp.py` parses the other two.

- **Evaluate the fire day, never the arm day.** The phone arms the evening
  before; "today's" ramp there is tomorrow's time plus a minute, every day.
- The PC clamps any synced time to *today's* ramp. A record up to 08:00 is
  expected lag (the phone publishes when the app runs) and logs INFO; only a
  time later than 08:00 is a WARNING.
- The one-shot earlier override lapses once the ramp catches up with it, and
  the ring screen re-arms the policy after `resetAfterFire` — `dismiss()`
  natively re-arms the *stored* time, i.e. the override just spent.
