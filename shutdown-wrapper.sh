#!/bin/bash
# Wrapper for /usr/bin/shutdown that redirects to rtcwake -m disk on alarm
# nights (every day of the week). This ensures that both the automated
# systemd timer AND manual "shutdown now" hibernate correctly so the PC
# wakes for the morning alarm.
#
# Install to /usr/local/bin/shutdown (takes priority over /usr/bin/shutdown
# because /usr/local/bin appears first in PATH).
#
# Wake time is taken from the private GitHub Gist written by the phone app
# (see phone_app/). Falls back to WAKE_AFTER_HOURS if the Gist is not
# configured or unreachable. Config: ~/.config/wake_alarm/gist_sync.json
# with keys "token" (GitHub PAT with gist scope) and "gist_id".

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

# Read alarm time from the private GitHub Gist written by the phone app.
# Returns the Unix epoch (seconds) of the next occurrence of the stored H:M.
# Exits non-zero if the Gist is not configured, unreachable, or malformed.
get_gist_alarm_epoch() {
    local cfg="$HOME/.config/wake_alarm/gist_sync.json"
    [[ -f "$cfg" ]] || return 1

    local token gist_id raw_content hour minute target_epoch now_epoch
    token=$(jq -r .token "$cfg" 2>/dev/null) || return 1
    gist_id=$(jq -r .gist_id "$cfg" 2>/dev/null) || return 1
    [[ -n "$token" && "$token" != "null" ]] || return 1
    [[ -n "$gist_id" && "$gist_id" != "null" ]] || return 1

    raw_content=$(curl -sf --max-time 10 \
        -H "Authorization: token $token" \
        "https://api.github.com/gists/$gist_id" \
        | jq -r '.files["wake_alarm_sync.json"].content') || return 1
    [[ -n "$raw_content" && "$raw_content" != "null" ]] || return 1

    hour=$(printf '%s' "$raw_content" | jq -r .alarm_hour 2>/dev/null) || return 1
    minute=$(printf '%s' "$raw_content" | jq -r .alarm_minute 2>/dev/null) || return 1
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
        if wake_epoch=$(get_gist_alarm_epoch 2>/dev/null); then
            logger -t shutdown-wrapper \
                "Gist sync: waking at $(date -d "@$wake_epoch") (epoch $wake_epoch)"
        else
            wake_epoch=$(( $(printf '%(%s)T' -1) + WAKE_AFTER_HOURS * 3600 ))
            logger -t shutdown-wrapper \
                "Gist unavailable — fallback +${WAKE_AFTER_HOURS}h (epoch $wake_epoch)"
        fi
        sudo "$RTCWAKE" -m no -t "$wake_epoch"
        exec /usr/bin/systemctl hibernate
        ;;
    *)
        exec "$REAL_SHUTDOWN" "$@"
        ;;
esac
