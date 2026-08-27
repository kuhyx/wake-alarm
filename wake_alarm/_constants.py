"""Constants for the weekend wake alarm system."""

from __future__ import annotations

from pathlib import Path

# Days the wake alarm is active (Python weekday(): Mon=0 ... Sun=6)
# Every day of the week.
ALARM_DAYS: frozenset[int] = frozenset({0, 1, 2, 3, 4, 5, 6})

# How many hours after shutdown the PC should wake.
# Only used by the hibernate fallback path (shutdown-wrapper.sh) for the rare
# night the PC is actually powered down; the primary path is the per-minute
# trigger timer, which reads the phone's alarm directly (see _trigger.py).
WAKE_AFTER_HOURS: int = 8

# Minutes after alarm starts within which you must dismiss to earn skip
DISMISS_WINDOW_MINUTES: int = 30

# Hour at which the alarm fires when the phone's alarm cannot be resolved at
# all — no network *and* no cached read ever written. Minute is implicitly 0.
FALLBACK_ALARM_HOUR: int = 13

# Alarm escalation phase boundaries (minutes from alarm start).
#
# Compressed to fit INSIDE the 5-minute failsafe window. They used to be 5 and
# 15, which -- once the failsafe was added at 300 s -- meant the alarm was
# silenced before it ever left the softest rung, and the medium and loud
# phases became unreachable code. The alarm has to reach its most annoying
# setting well before it goes quiet, or waiting out five minutes in bed is a
# winning strategy.
PHASE_SOFT_END: int = 1
PHASE_MEDIUM_END: int = 2
# After PHASE_MEDIUM_END: alternating loud tones until the failsafe silences.

# Beep intervals per phase (seconds)
SOFT_BEEP_INTERVAL: float = 5.0
MEDIUM_BEEP_INTERVAL: float = 3.0
LOUD_TOGGLE_INTERVAL: float = 2.0

# Dismiss challenge: length of the random code
DISMISS_CODE_LENGTH: int = 10
# Number of correct code entries required to dismiss the alarm.
# Requiring more than one round forces the user to stay awake long enough
# to actually read and type multiple independent codes.
DISMISS_ROUNDS_REQUIRED: int = 4
# Seconds the code is visible before being hidden in a flash challenge.
DISMISS_FLASH_SECONDS: int = 4
# How often the dismiss code refreshes (seconds)
DISMISS_CODE_REFRESH_SECONDS: int = 30

# State file for wake alarm (HMAC-signed)
WAKE_STATE_FILE: Path = Path(__file__).resolve().parent / "wake_state.json"

# rtcwake binary path
RTCWAKE_BIN: str = "/usr/sbin/rtcwake"

# Preferred alarm audio output (machine-specific, empirically verified).
# At wake time the Bluetooth speaker is disconnected and PipeWire often has only
# the auto_null sink, so the alarm activates every card and plays on all sinks.
# This is the G27Q monitor's built-in HDMI speaker — the one always-present
# output on this machine — used as the preferred default sink when present.
ALARM_AUDIO_SINK: str = "alsa_output.pci-0000_01_00.1.hdmi-stereo"

# Path to the workout log written by the companion screen_locker package.
# Dict keyed by YYYY-MM-DD date strings; presence of today's key means the
# workout was already completed and the alarm should not fire.
WORKOUT_LOG_FILE: Path = (
    Path.home() / "screen-locker" / "screen_locker" / "workout_log.json"
)

# --- Phone alarm sync (crdt_sync over GitHub) -----------------------------
# The phone app pushes its alarm to a private repo as a crdt_sync log; the PC
# reads it back. shutdown-wrapper.sh reads the SAME file with jq for the
# hibernate fallback — keep the two readers in step if any of this changes.

# GitHub token config, key "token" (PAT with "repo" scope: the repo is private).
# The alarm's escape-hatch history. Lives beside the sync config rather
# than in the package dir, so a reinstall cannot silently reset the budget.
ESCAPE_HISTORY_FILE: Path = (
    Path.home() / ".config" / "wake_alarm" / "escape_history.json"
)
# How long the alarm must have been up before the hatch is offered, so it
# is never the easy first move.
#
# Deliberately NOT equal to FAILSAFE_SILENCE_SECONDS. Both used to sit at 300,
# which meant the sound stopped and the escape hatch appeared in the same
# instant -- making the hatch far more attractive than it was designed to be,
# exactly when the alarm had just stopped being annoying.
ESCAPE_OFFER_AFTER_SECONDS: int = 900

# Pause between powering the smart plug and the first beep. A powered
# speaker's soft-start / mute relay typically delays output 1-5 s after mains
# is applied, so firing the plug and the first tone together loses the opening
# of the alarm. Costs nothing when no plug is configured.
PLUG_PREROLL_SECONDS: float = 4.0

# The fire-time session record. Beside the sync config rather than in the
# package dir, so a reinstall cannot erase evidence that an alarm was cut
# short. Distinct from WAKE_STATE_FILE, which records only *dismissal* and is
# also read cross-repo by screen_locker/_wake_state.py.
ALARM_SESSION_FILE: Path = Path.home() / ".config" / "wake_alarm" / "alarm_session.json"

# How long after fire time an unfinished session still re-fires the alarm.
# Bounded because nothing clears the record when the alarm process dies before
# dismissal: unbounded, a crash at startup would restart the alarm every minute
# forever. Long enough to survive a power-off plus a boot, short enough that a
# session can never leak into the following night.
REFIRE_MAX_AGE_SECONDS: float = 5400.0

# How far a session record may be stamped in the *future* and still count as
# ringing. A backward clock jump (NTP correcting after a resume, RTC skew at
# boot) is routine on a machine that hibernates nightly, and discarding such a
# record would fail open on exactly the power-off escape the record closes.
# Bounded so a wildly wrong RTC still cannot create an endless re-fire.
CLOCK_SKEW_TOLERANCE_SECONDS: float = 900.0

# --- Power-button inhibitor (item 2) --------------------------------------
# What logind is asked to block while the alarm rings. handle-power-key stops
# the short press; shutdown and idle stop a scripted poweroff and the idle
# timer from doing the same job by another route.
INHIBIT_WHAT: str = "handle-power-key:shutdown:idle"

# The --who string. Also the pkill pattern used to clear a stale blocker from a
# crashed alarm, so it must stay distinctive.
INHIBIT_WHO: str = "wake-alarm"
INHIBIT_WHY: str = "Wake alarm is ringing and must be dismissed, not switched off"

# The inhibitor child self-terminates after this long even if nobody releases
# it. An orphaned block-mode inhibitor holding handle-power-key would leave the
# power button dead until reboot -- a worse failure than the one being fixed --
# so it is never `sleep infinity`. Comfortably longer than any real alarm.
INHIBIT_MAX_SECONDS: float = 7200.0

# How long to wait for the inhibitor child to prove it survived. Popen
# succeeding only means the binary launched; logind can still refuse (polkit
# denies a non-interactive session, seen in a vmbox run: "Failed to inhibit:
# Access denied", exit 1). Still alive after this means the inhibit was
# accepted. Short enough not to delay the alarm perceptibly.
INHIBIT_CONFIRM_SECONDS: float = 0.5

# When the failsafe silences the alarm. Audio ONLY: the lock, the typed
# challenge and the workout gate all persist past this point, so waiting it
# out in bed is not a way to escape the alarm. It exists so a ring nobody is
# present to dismiss does not sound indefinitely.
FAILSAFE_SILENCE_SECONDS: float = 300.0

SYNC_CONFIG_FILE: Path = Path.home() / ".config" / "wake_alarm" / "sync.json"

# Fallback token locations, tried in order when SYNC_CONFIG_FILE is absent.
# The sibling companion apps already store a repo-scoped PAT for this same
# kuhyx/syncs repo as a raw single-line file, so reusing one means a single
# token to rotate instead of three copies drifting out of sync.
# shutdown-wrapper.sh reads the same list — keep the two in step.
SYNC_TOKEN_FALLBACK_FILES: tuple[Path, ...] = (
    Path.home() / ".config" / "diet_guard" / "sync_token",
    Path.home() / ".config" / "screen_locker" / "sync_token",
)

# Where a successful read is cached, so a network blip can't cost a wake-up.
ALARM_CACHE_FILE: Path = Path.home() / ".config" / "wake_alarm" / "alarm_cache.json"

# Delays between card-profile reactivation passes while the alarm rings.
# The G27Q's HDMI sink takes ~15 s to enumerate after the monitor wakes, and
# until its card profile is switched on the sink does not exist at all -- so
# re-enumerating sinks alone can never find it. Decaying schedule: dense early
# (when outputs are still arriving), sparse later, stopping at ~2 minutes.
REACTIVATE_ATTEMPT_DELAYS: tuple[float, ...] = (3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0)

# Structured logs live under XDG state, not .config: they are churning runtime
# data, not configuration. The JSONL file is additive -- the journal keeps
# receiving the same records via stderr.
LOG_STATE_DIR: Path = Path.home() / ".local" / "state" / "wake_alarm"
LOG_JSONL_FILE: Path = LOG_STATE_DIR / "events.jsonl"

# Fingerprint of the last emitted event, so consecutive duplicates can be
# suppressed across separate per-minute trigger processes.
LOG_DEDUPE_FILE: Path = LOG_STATE_DIR / "last_event.json"

# The phone's path to its published alarm. Deliberately the *same* logical
# path on both backends — Firebase's namespace mirrors the repo layout — so
# only the transport changes, never the parse.
#
# This is the *legacy* path: the phone used to be the sole writer under the
# fixed device id "phone". It still is in practice, but the id is migrating
# to a per-install uuid, so the reader discovers device directories under
# SYNC_DEVICES_PREFIX and falls back to this path for a phone that has not
# yet published under its uuid. Keep reading it until every install has
# migrated; deleting it early means a stale phone's alarm silently stops
# being seen, and the trigger falls back to FALLBACK_ALARM_HOUR.
SYNC_ALARM_PATH: str = "wake-alarm-sync/devices/phone/alarm.json"

# The directory holding one subdirectory per publishing device.
SYNC_DEVICES_PREFIX: str = "wake-alarm-sync/devices"

# The file each device publishes its alarm as, inside its own directory.
SYNC_ALARM_FILENAME: str = "alarm.json"

# Names this app's credential cache under ~/.local/share/crdt-sync/, keeping
# its Firebase refresh token separate from the sibling apps'.
SYNC_APP_NAME: str = "wake_alarm"

# The shared private repo, used only by the GitHub fallback path. Retiring the
# mirror means deleting these three and _fetch_github_alarm() together.
SYNC_API_BASE: str = "https://api.github.com"
SYNC_REPO_OWNER: str = "kuhyx"
SYNC_REPO_NAME: str = "syncs"

# Valid ranges for a wall-clock alarm, used to reject a malformed sync payload
# or a corrupted cache before it can become a fire time.
MIN_HOUR: int = 0
MAX_HOUR: int = 23
MIN_MINUTE: int = 0
MAX_MINUTE: int = 59

# Timeout for the Contents API read. Short: a slow read must never delay the
# per-minute trigger tick, and a stale cache is a perfectly good answer.
SYNC_HTTP_TIMEOUT_SECONDS: float = 10.0

# How long a cached alarm is served without re-fetching. The trigger ticks once
# a minute (so firing lands on the exact minute), but only touches the network
# when the cache is older than this — bounding phone->PC latency at ~5 minutes
# while keeping GitHub reads to ~288/day.
ALARM_CACHE_MAX_AGE_SECONDS: float = 300.0

# How long after the alarm instant the trigger will still fire. Covers a
# suspended PC, a missed timer tick, and a machine booted mid-window. Also the
# reason a phone alarm moved *earlier* mid-window still fires promptly.
TRIGGER_CATCHUP_MINUTES: int = 60

# The unit the trigger starts. Deliberately the orchestrator, never
# wake-alarm.service directly: the orchestrator runs the alarm first and the
# workout lock after, so the two never fight for the fullscreen.
TRIGGER_TARGET_UNIT: str = "morning-routine.service"

# TP-Link Tapo P110 smart-plug config file (JSON).
# Create with mode 0600 and these keys: host, email, password.
# Example contents: a JSON object mapping host -> "192.168.x.x", email ->
# "tapo@example.com" and password -> "your-password".
# Missing/invalid file => smart-plug control is skipped silently.
TAPO_CONFIG_FILE: Path = Path.home() / ".config" / "wake_alarm" / "tapo.json"

# Timeout (seconds) for a single Tapo plug operation. Keep short so a
# missing/unreachable plug never delays the alarm by more than this.
TAPO_TIMEOUT_SECONDS: float = 5.0
