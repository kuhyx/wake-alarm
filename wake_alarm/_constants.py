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

# Alarm escalation phase boundaries (minutes from alarm start)
PHASE_SOFT_END: int = 5
PHASE_MEDIUM_END: int = 15
# After PHASE_MEDIUM_END: continuous sine tone until dismiss window closes

# Beep intervals per phase (seconds)
SOFT_BEEP_INTERVAL: float = 10.0
MEDIUM_BEEP_INTERVAL: float = 5.0
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
ESCAPE_OFFER_AFTER_SECONDS: int = 300

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

# The shared private repo every companion app syncs through, and the phone's
# path within it. The phone is the sole writer under a fixed device id, so one
# read of its alarm.json is enough — no device discovery or HLC ordering here.
SYNC_API_BASE: str = "https://api.github.com"
SYNC_REPO_OWNER: str = "kuhyx"
SYNC_REPO_NAME: str = "syncs"
SYNC_ALARM_PATH: str = "wake-alarm-sync/devices/phone/alarm.json"

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
