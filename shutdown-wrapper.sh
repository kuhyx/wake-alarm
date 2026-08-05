#!/bin/bash
# Wrapper for /usr/bin/shutdown that redirects to rtcwake -m disk on alarm
# nights (every day of the week). This ensures that both the automated
# systemd timer AND manual "shutdown now" hibernate correctly so the PC
# wakes for the morning alarm.
#
# Install to /usr/local/bin/shutdown (takes priority over /usr/bin/shutdown
# because /usr/local/bin appears first in PATH).
#
# This is the FALLBACK path, for the rare night the PC is actually powered
# down. The primary path is wake-alarm-trigger.timer, which ticks once a
# minute on the always-on machine and fires at the phone's alarm time without
# any rtcwake involvement (see wake_alarm/_trigger.py).
#
# Wake time is read from ~/.config/wake_alarm/alarm_cache.json, the on-disk
# cache that wake-alarm-trigger.timer refreshes every minute from the alarm
# the phone app pushes. Falls back to WAKE_AFTER_HOURS if that cache is
# missing or unusable.
#
# Deliberately a *local file read*, with no network call and no credentials.
# This script runs as /usr/local/bin/shutdown, at the one moment the machine
# is going down; a remote fetch there can block on a dying network, and under
# Firebase it could not work at all, because an ID token lasts about an hour
# and refreshing one is beyond what a shell script should be doing with a
# secret. The Python side already holds the credentials and already keeps this
# cache fresh, so the backend it syncs against is now invisible here: this
# wrapper needs no changes when GitHub is retired.
#
# The trade-off is bounded and acceptable: a cache older than the trigger's
# refresh interval still reflects the last alarm the phone published, and the
# alarm changes far more rarely than once a minute. MAX_CACHE_AGE_SECONDS
# below only rejects a cache so old it suggests the trigger has been dead for
# days, in which case the fixed fallback is the safer answer.

set -euo pipefail

REAL_SHUTDOWN=/usr/bin/shutdown
RTCWAKE=/usr/sbin/rtcwake
# Fallback: how many hours after shutdown to wake when Gist is unavailable.
# Must match WAKE_AFTER_HOURS in wake_alarm/_constants.py.
WAKE_AFTER_HOURS=8

# Pass through reboots and cancel commands unchanged.
for arg in "$@"; do
    case "$arg" in
        -r|--reboot|-c|--cancel)
            exec "$REAL_SHUTDOWN" "$@"
            ;;
    esac
done

ALARM_CACHE="$HOME/.config/wake_alarm/alarm_cache.json"
# Reject a cache this old as evidence the trigger itself has stopped running.
# Generous on purpose (2 days): the alarm rarely changes, so a merely stale
# cache is still a far better answer than the fixed +8h fallback. Mirrors
# ALARM_CACHE_FILE in wake_alarm/_constants.py.
MAX_CACHE_AGE_SECONDS=$(( 2 * 24 * 3600 ))

# Read the alarm the phone published, from the local cache the trigger keeps
# fresh. Returns the Unix epoch (seconds) of the next occurrence of that H:M.
# Exits non-zero if the cache is absent, malformed, or older than
# MAX_CACHE_AGE_SECONDS, so the caller can fall back.
#
# The cache is written by wake_alarm/_sync.py as
# {"hour": H, "minute": M, "fetched_at": <unix seconds>} — keep this reader in
# step with _write_cache() there. Storing H/M rather than the raw crdt_sync log
# means this script no longer needs to understand the sync payload format at
# all, which is what makes it backend-agnostic.
get_synced_alarm_epoch() {
    local hour minute fetched_at now_epoch age target_epoch

    [[ -f "$ALARM_CACHE" ]] || return 1

    # One jq call for all three fields: -e fails on null, and the fixed field
    # order lets a single read destructure them.
    read -r hour minute fetched_at < <(
        jq -er '"\(.hour) \(.minute) \(.fetched_at)"' "$ALARM_CACHE" 2>/dev/null
    ) || return 1

    [[ "$hour" =~ ^[0-9]+$ && "$minute" =~ ^[0-9]+$ ]] || return 1
    (( hour <= 23 && minute <= 59 )) || return 1

    printf -v now_epoch '%(%s)T' -1
    # fetched_at is a float; strip the fraction rather than pulling in bc.
    age=$(( now_epoch - ${fetched_at%%.*} ))
    (( age >= 0 && age <= MAX_CACHE_AGE_SECONDS )) || return 1

    target_epoch=$(date -d "today $hour:$minute" +%s)
    if (( target_epoch <= now_epoch )); then
        target_epoch=$(date -d "tomorrow $hour:$minute" +%s)
    fi
    echo "$target_epoch"
}

# Every day of the week is an alarm day (date +%u: Mon=1 … Sun=7).
tomorrow_dow=$(date -d "tomorrow" +%u)
case "$tomorrow_dow" in
    1|2|3|4|5|6|7)
        if wake_epoch=$(get_synced_alarm_epoch 2>/dev/null); then
            logger -t shutdown-wrapper \
                "alarm cache: waking at $(date -d "@$wake_epoch") (epoch $wake_epoch)"
        else
            wake_epoch=$(( $(printf '%(%s)T' -1) + WAKE_AFTER_HOURS * 3600 ))
            logger -t shutdown-wrapper \
                "alarm cache unusable — fallback +${WAKE_AFTER_HOURS}h (epoch $wake_epoch)"
        fi
        sudo "$RTCWAKE" -m no -t "$wake_epoch"
        exec /usr/bin/systemctl hibernate
        ;;
    *)
        exec "$REAL_SHUTDOWN" "$@"
        ;;
esac
