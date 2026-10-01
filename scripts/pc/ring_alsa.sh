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

play() {
    aplay -q -D "$DEVICE" "$1" || sleep "$RETRY_SECONDS"
}

main() {
    [[ $# -eq 2 ]] || usage
    local rise="$1" loop="$2"
    [[ -r "$rise" && -r "$loop" ]] || {
        echo "Error: cannot read $rise / $loop" >&2
        exit 1
    }
    unmute_all
    play "$rise"
    while true; do
        play "$loop"
    done
}

main "$@"
