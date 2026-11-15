#!/bin/bash
# ============================================================================
# Ring the PC speakers straight through ALSA, as root.
#
# ExecStart of wake-alarm-ring-alsa.service (installed to
# /usr/local/lib/wake-alarm/). Used by the PC fallback alarm when no
# graphical session owns the sound (night lockdown: nobody logged in, and
# the user is not in `audio`). Unmutes and maxes every playback control the
# speakers' card has, plays the rising WAV once, then loops the full-volume
# one until systemd stops the unit (RuntimeMaxSec is the backstop).
#
# When the card is held (almost always the user's PipeWire), the FIRST busy
# open -- no retries -- hands the ring to PipeWire as the user
# (wake_alarm._ring_main, via runuser). Killing the holder first would kill
# the PipeWire that fallback needs. Only if that fallback also fails: one
# `fuser -k -TERM` on the card's playback nodes, one more ALSA try, then exit
# non-zero. Needs WAKE_ALARM_USER (set by the unit; install.sh fills it in)
# and psmisc's fuser.
#
# Usage: ring_alsa.sh <rise.wav> <loop.wav>
# ============================================================================

set -euo pipefail

# The speakers: ALC897 Analog on the motherboard codec (`aplay -l`).
# Overridable only so the vmbox gate can aim it at snd-dummy.
readonly CARD="${WAKE_ALARM_CARD:-Generic_1}"
readonly DEVICE="plughw:CARD=${CARD},DEV=0"
# Playback controls that may gate the speakers; only those present are set.
# Front is the rear line-out jack on this board.
readonly CONTROLS=(Master PCM Speaker Headphone Front)
# The user whose PipeWire owns the card, and the interpreter that has the
# wake_alarm package (system python, same as the user timers).
readonly RING_USER="${WAKE_ALARM_USER:-}"
readonly PY="${WAKE_ALARM_PYTHON:-/usr/bin/python3}"
# A failed aplay (device briefly held elsewhere) must not spin the CPU.
readonly RETRY_SECONDS=1

usage() {
    echo "Usage: $(basename "$0") <rise.wav> <loop.wav>" >&2
    exit 2
}

unmute_all() {
    local control
    for control in "${CONTROLS[@]}"; do
        if amixer -c "$CARD" sget "$control" >/dev/null 2>&1; then
            # Volume and switch separately: a control may have only one.
            amixer -q -c "$CARD" sset "$control" 100% >/dev/null 2>&1 || true
            amixer -q -c "$CARD" sset "$control" unmute >/dev/null 2>&1 || true
            echo "set $control to 100%, unmuted"
        fi
    done
}

# aplay's stderr says why it failed; only "busy" triggers the fallback.
play() {
    local err
    err="$(mktemp)"
    if aplay -q -D "$DEVICE" "$1" 2>"$err"; then
        rm -f "$err"
        return 0
    fi
    if grep -qi 'busy' "$err"; then
        rm -f "$err"
        return 3
    fi
    cat "$err" >&2
    rm -f "$err"
    sleep "$RETRY_SECONDS"
}

# Ring through the user's PipeWire until systemd's SIGTERM; non-zero if it
# cannot play (the fallback itself reports ring_backend FAILED).
user_fallback() {
    [[ -n "$RING_USER" ]] || return 1
    local uid home
    uid="$(id -u "$RING_USER")"
    home="$(getent passwd "$RING_USER" | cut -d: -f6)"
    echo "fallback-started: card busy, ringing through PipeWire as $RING_USER"
    runuser -u "$RING_USER" -- env HOME="$home" PATH="$PATH" \
        XDG_RUNTIME_DIR="/run/user/$uid" \
        "$PY" -m wake_alarm._ring_main "$1" "$2"
}

# Last resort: free the card from whatever holds it, once.
kill_holder() {
    local node
    node="$(readlink "/proc/asound/$CARD")" || return 0
    echo "kill-holder: fuser -k -TERM on ${node}"
    # shellcheck disable=SC2046  # one argument per playback node, by design
    fuser -k -TERM $(compgen -G "/dev/snd/pcmC${node#card}D*p") 2>&1 || true
    sleep "$RETRY_SECONDS"
}

# The card was busy on its first open: PipeWire first, then kill, then fail.
# Returns only when the holder was killed and ALSA works again.
handle_busy() {
    local rise="$1" loop="$2"
    if user_fallback "$rise" "$loop"; then
        exit 0
    fi
    echo "fallback-failed: killing the holder, one more ALSA try" >&2
    kill_holder
    aplay -q -D "$DEVICE" "$rise" || {
        echo "Error: card $CARD still unusable" >&2
        exit 1
    }
}

main() {
    [[ $# -eq 2 ]] || usage
    local rise="$1" loop="$2"
    [[ -r "$rise" && -r "$loop" ]] || {
        echo "Error: cannot read $rise / $loop" >&2
        exit 1
    }
    unmute_all
    local rc=0
    play "$rise" || rc=$?
    [[ $rc -ne 3 ]] || handle_busy "$rise" "$loop"
    while true; do
        play "$loop" || sleep "$RETRY_SECONDS"
    done
}

main "$@"
