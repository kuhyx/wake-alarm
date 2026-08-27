# wake_alarm architecture

Reference for the module layout after the 2026-08-26 split, and the two
failure modes that motivated it.

## Where behaviour lives

`_alarm.py` owns the window and the dismiss flow and nothing else. When looking
for behaviour, start here:

| Question | Module |
|---|---|
| Should the alarm run at all today? | `_gating` (no time gate — that is `_trigger`) |
| What should it sound like right now? | `_escalation` (pure), driven by `_beep_loop` |
| Why did it go quiet? | `_escalation` — the failsafe at `FAILSAFE_SILENCE_SECONDS` |
| Why is there no sound on HDMI? | `_sinks` + `_reactivate` (see below) |
| Challenge presentation / rounds | `_rounds`, `_countdown`, `_dismiss_view` |
| Recurring timers | `_alarm_timers` (a mixin; they reschedule via `root.after`) |
| Screen flash | `_screen_flash` (~1.3 Hz, deliberately under the 3 Hz threshold) |
| Startup hardware | `_startup` (display, brightness, plug + pre-roll) |
| Structured logs | `_logging_setup`, `_log_sink`, `_log_dedupe`, `_correlation` |

### The audio failure this fixed

`_activate_all_outputs()` ran **once**, at startup, and `_parse_profile_line`
drops any profile reporting `available: no`. At wake time the monitor has not
finished its HDMI handshake, so the profile is skipped — and while a card's
profile is `off` its sink **does not exist**, so `_play_on_all_sinks`'s
per-cycle re-enumeration can never find it. `_reactivate` re-runs activation on
a decaying schedule and logs the enumerated sink list each pass.

A **powered-off speaker is not detectable from software** — the analog sink is
present and `IDLE` either way. That is a hardware problem; see
`DOCS-speaker-recommendation.md`.

### Timing constants that must not collide

`FAILSAFE_SILENCE_SECONDS` (300) silences **audio only**; the lock, challenge
and workout gate persist. Two invariants are locked in by tests in
`test_escalation.py`, because breaking either silently guts the alarm:

- `PHASE_MEDIUM_END * 60 < FAILSAFE_SILENCE_SECONDS` — otherwise the escalation
  never leaves its softest rung before going quiet.
- `ESCAPE_OFFER_AFTER_SECONDS` (900) `> FAILSAFE_SILENCE_SECONDS` — otherwise
  the escape hatch appears exactly as the alarm stops being annoying.

