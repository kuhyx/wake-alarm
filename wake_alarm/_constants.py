"""Constants for the wake-alarm trigger and the phone-alarm sync.

The PC no longer wakes anyone -- the phone does. What is left here is what
the per-minute trigger needs to answer two questions: what time did the phone
say, and has the morning routine already started today.
"""

from __future__ import annotations

from datetime import date, timedelta
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
# diet_guard already stores a repo-scoped PAT for this same kuhyx/syncs repo as
# a raw single-line file; reusing it means one token to rotate, not two.
# screen-locker's sync_token is gone: its PC sync is Firebase-only since
# 2026-10-09 and nothing maintains that file any more.
SYNC_TOKEN_FALLBACK_FILES: tuple[Path, ...] = (
    Path.home() / ".config" / "diet_guard" / "sync_token",
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
# How old the phone's *published* record may be before the PC stops trusting
# it. Distinct from ALARM_CACHE_MAX_AGE_SECONDS, which is about how recently
# *we fetched*: a value fetched five seconds ago can still be a time the phone
# chose months back and has since moved on from.
#
# This exists because that is exactly what happened. A publishing bug on the
# phone left one record stamped 2026-08-09, and the PC honoured it faithfully
# for three weeks -- a publish that never happens is indistinguishable from one
# that has not changed, so the last successful publish is authoritative
# forever. Expiring to FALLBACK_ALARM_HOUR is safe precisely because that
# constant is the phone's own baseline, so a lapsed record degrades to the
# right answer rather than a guess.
PUBLISHED_ALARM_MAX_AGE_SECONDS: float = 14 * 24 * 60 * 60

ALARM_CACHE_MAX_AGE_SECONDS: float = 300.0

# How long after the alarm instant the trigger will still fire. Covers a
# suspended PC, a missed timer tick, and a machine booted mid-window. Also the
# reason a phone alarm moved *earlier* mid-window still fires promptly.
TRIGGER_CATCHUP_MINUTES: int = 60

# The unit the trigger starts. Deliberately the orchestrator, never
# wake-alarm.service directly: the orchestrator runs the alarm first and the
# workout lock after, so the two never fight for the fullscreen.
TRIGGER_TARGET_UNIT: str = "morning-routine.service"


# --- Morning session (phone -> PC carrot) ----------------------------------
# The phone publishes its morning session on the same alarm.json record; the
# PC distils it into one HMAC-signed file that screen-locker and leetcode-guard
# read with stdlib only. Both consumers hardcode this path -- keep in step.
MORNING_SESSION_FILE: Path = LOG_STATE_DIR / "morning_session.json"

# crdt_sync field names on alarm.json (session_sync.dart owns the writer side).
SESSIONS_FIELD: str = "morning_sessions"
SESSION_CURRENT_FIELD: str = "current_session"
ENERGY_FIELD: str = "latest_energy"

# A session that has started but not finished is exempt only for as long as an
# honest morning takes, and never past the cap: relative to the start, because
# an alarm earlier than 08:00 is legal and a fixed 09:30 would hand an aborted
# 06:15 session three hours of no lock. A completed session earns the flat end.
SESSION_PROVISIONAL_GRACE: timedelta = timedelta(minutes=90)
SESSION_PROVISIONAL_CAP: tuple[int, int] = (9, 30)
SESSION_COMPLETED_UNTIL: tuple[int, int] = (11, 0)

# Before the alarm, being up is the goal, not an offence: a day with no
# session yet is exempt until the alarm has rung and had time to be
# dismissed (ring -> tags -> steps -> answers -> the start publish reaches the
# PC). A phone switched off at the alarm locks this long after it.
SESSION_NONE_GRACE: timedelta = timedelta(minutes=15)

# A PC booted mid-morning often has no DNS for its first seconds (2026-11-07:
# one try at 07:48:43, exit 1, next timer tick at 07:50). ``--refresh`` keeps
# trying in-process this long, every REFRESH_POLL_SECONDS, before giving up.
# Consumers (gatelock.morning_session) wait up to 180 s, so this stays under.
REFRESH_RETRY_SECONDS: int = 150
REFRESH_POLL_SECONDS: int = 5


# Workday stick (a Tue/Wed/Thu miss -> tomorrow loses its leniency). The days
# themselves are freedays.WORKDAYS, the one set every gate app reads.
WORKDAY_PENALTY_FILE: Path = LOG_STATE_DIR / "workday_penalty.json"


# --- Wake enforcement v2 (DOCS-wake-enforcement.md is the contract) -----------
# These names are read by test_stakes_mirrors.py against the phone's Dart
# constants: rename one here and there in the same commit.

# PC fallback alarm, all relative to today's alarm A (clamped <= 08:00):
# ring when the phone has not opened its ring screen by A + 2 min, stop after
# 30 min of ringing, and never start a ring past A + 45 min.
FALLBACK_PHONE_SILENT_AFTER: timedelta = timedelta(minutes=2)
FALLBACK_RING_CAP: timedelta = timedelta(minutes=30)
FALLBACK_WINDOW_END: timedelta = timedelta(minutes=45)

# The PC arms its RTC this long before a stick-day alarm, so it is up (resumed
# from hibernate, or booted) and has synced by the time the phone rings.
RTC_WAKE_LEAD: timedelta = timedelta(minutes=10)

# Phone stick: a streak of n consecutive stick-day misses locks today plus
# min(n, 4) days -- five calendar days at most.
STICK_LOCKDOWN_MAX_DAYS: int = 5

# The "That was a bug" escape hatch is honoured for mornings up to and
# including this date, and only with a reason at least this long.
ESCAPE_HATCH_LAST_DAY: date = date(2026, 10, 15)
ESCAPE_REASON_MIN_CHARS: int = 40

# Today's fallback-ring latch: {"date", "started_at", "stopped_at", "reason",
# "stop_reason"}.
FALLBACK_RING_FILE: Path = LOG_STATE_DIR / "fallback_ring.json"

# {"mode": "hibernate" | "poweroff"}; how the PC goes down for the night.
PC_WAKE_CONFIG: Path = Path.home() / ".config" / "wake_alarm" / "pc_wake.json"

# The daily audit's reports. Outside the repo on purpose: personal data.
INCIDENTS_DIR: Path = Path.home() / "data" / "wake-alarm" / "incidents"

# The RTC alarm _rtc last armed ({"epoch", "target_date"}), so a disarm
# only ever clears an alarm this package set.
RTC_ARMED_FILE: Path = LOG_STATE_DIR / "rtc_armed.json"

# Last value logged per change-only event (fallback_tick, rtc_armed, ...), so
# a per-minute or per-15-minute job logs a decision once, not every run.
EVENT_STATE_FILE: Path = LOG_STATE_DIR / "event_state.json"

# crdt_sync field names on alarm.json for the v2 fields (phone writes them).
RING_STARTED_FIELD: str = "ring_started"
ESCAPES_FIELD: str = "escapes"
STICK_STATE_FIELD: str = "stick_state"
PHONE_EVENTS_FIELD: str = "phone_events"
