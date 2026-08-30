"""Constants for the wake-alarm trigger and the phone-alarm sync.

The PC no longer wakes anyone -- the phone does. What is left here is what
the per-minute trigger needs to answer two questions: what time did the phone
say, and has the morning routine already started today.
"""

from __future__ import annotations

from pathlib import Path

# Days the wake alarm is active (Python weekday(): Mon=0 ... Sun=6)
# Every day of the week.
ALARM_DAYS: frozenset[int] = frozenset({0, 1, 2, 3, 4, 5, 6})


# Hour at which the alarm fires when the phone's alarm cannot be resolved at
# all — no network *and* no cached read ever written. Minute is implicitly 0.
#
# Deliberately the SAME baseline the phone bakes in (AlarmPolicy.baselineHour),
# so the two halves agree even with the network down. It used to be 13:00,
# which meant a Firebase outage silently moved the alarm five hours later —
# the one direction the whole design refuses to allow.
FALLBACK_ALARM_HOUR: int = 8


# State file for wake alarm (HMAC-signed)
WAKE_STATE_FILE: Path = Path(__file__).resolve().parent / "wake_state.json"


# --- Phone alarm sync (crdt_sync over GitHub) -----------------------------
# The phone app pushes its alarm to a private repo as a crdt_sync log; the PC
# reads it back. shutdown-wrapper.sh reads the SAME file with jq for the
# hibernate fallback — keep the two readers in step if any of this changes.


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
