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
# Wake time is taken from the alarm the phone app pushes to the private
# kuhyx/syncs repo via the shared crdt_sync transport (see phone_app/). Falls
# back to WAKE_AFTER_HOURS if sync is not configured or unreachable. Token:
# ~/.config/wake_alarm/sync.json key "token", else a sibling app's
# ~/.config/{diet_guard,screen_locker}/sync_token. Needs "repo" scope, since
# the Contents API must read a private repo.

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

# Resolve the GitHub token, preferring wake_alarm's own JSON config and falling
# back to the sibling companion apps' raw single-line token files (one
# repo-scoped PAT covers every app syncing through kuhyx/syncs).
# Mirrors SYNC_CONFIG_FILE / SYNC_TOKEN_FALLBACK_FILES in
# wake_alarm/_constants.py — keep the two readers in step.
read_sync_token() {
    local cfg="$HOME/.config/wake_alarm/sync.json"
    local token fallback

    if [[ -f "$cfg" ]]; then
        token=$(jq -r '.token // empty' "$cfg" 2>/dev/null) || token=""
        if [[ -n "$token" ]]; then
            printf '%s' "$token"
            return 0
        fi
    fi

    for fallback in \
        "$HOME/.config/diet_guard/sync_token" \
        "$HOME/.config/screen_locker/sync_token"; do
        [[ -f "$fallback" ]] || continue
        token=$(tr -d '[:space:]' < "$fallback") || continue
        if [[ -n "$token" ]]; then
            printf '%s' "$token"
            return 0
        fi
    done

    return 1
}

# Read the alarm time the phone pushed to kuhyx/syncs via crdt_sync.
# Returns the Unix epoch (seconds) of the next occurrence of the stored H:M.
# Exits non-zero if sync is not configured, unreachable, or malformed.
#
# The phone is the sole writer, under the fixed device id "phone", so a single
# Contents-API read of its alarm.json is enough (no device discovery / HLC
# ordering needed here — that would only matter with multiple writers). The
# stored payload is a crdt_sync Log: {"alarm": {"fields": {"alarm_hour":
# [H, "<hlc>"], "alarm_minute": [M, "<hlc>"]}, ...}}. The raw media type makes
# the Contents API return that JSON directly, so no base64 decode is needed.
get_synced_alarm_epoch() {
    local token log_json hour minute target_epoch now_epoch
    token=$(read_sync_token) || return 1

    local url="https://api.github.com/repos/kuhyx/syncs/contents"
    url="$url/wake-alarm-sync/devices/phone/alarm.json"
    log_json=$(curl -sf --max-time 10 \
        -H "Authorization: token $token" \
        -H "Accept: application/vnd.github.raw" \
        "$url") || return 1
    [[ -n "$log_json" ]] || return 1

    hour=$(printf '%s' "$log_json" \
        | jq -r '.alarm.fields.alarm_hour[0]' 2>/dev/null) || return 1
    minute=$(printf '%s' "$log_json" \
        | jq -r '.alarm.fields.alarm_minute[0]' 2>/dev/null) || return 1
    [[ "$hour" =~ ^[0-9]+$ && "$minute" =~ ^[0-9]+$ ]] || return 1

    printf -v now_epoch '%(%s)T' -1
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
                "crdt_sync: waking at $(date -d "@$wake_epoch") (epoch $wake_epoch)"
        else
            wake_epoch=$(( $(printf '%(%s)T' -1) + WAKE_AFTER_HOURS * 3600 ))
            logger -t shutdown-wrapper \
                "sync unavailable — fallback +${WAKE_AFTER_HOURS}h (epoch $wake_epoch)"
        fi
        sudo "$RTCWAKE" -m no -t "$wake_epoch"
        exec /usr/bin/systemctl hibernate
        ;;
    *)
        exec "$REAL_SHUTDOWN" "$@"
        ;;
esac
