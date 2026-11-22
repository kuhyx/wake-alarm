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
# The monitors ring too (2026-11-22): kuhy switches the speakers off at the
# knob for the night, so the 07:51 ring of 11-22 played 30 min into silence.
# Every HDMI/DP output whose ELD names a connected monitor gets its own
# aplay loop, IEC958 unmuted; each output logs one `ring_sink` line.
#
# --probe proves the monitors without a sound: two seconds of digital
# silence to each, IEC958 muted, one `ring_probe` line per sink, exit 1 when
# any fails or none is connected (wake-alarm-ring-probe.service).
#
# --monitors <rise> <loop> rings only the monitors, until SIGTERM: the
# PipeWire path runs it as the user beside pw-play (wake_alarm/_ring_monitors).
#
# Usage: ring_alsa.sh <rise.wav> <loop.wav> | --monitors <rise> <loop> | --probe
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
# How long a monitor's aplay must survive to count as opened.
readonly OPEN_CHECK_SECONDS=1
# The monitors as card:dev:name:hdmi-index lines; unset = read `aplay -l`.
# Set (even empty) only by the vmbox gate.
MONITORS_OVERRIDE="${WAKE_ALARM_MONITORS-__unset__}"
readonly MONITORS_OVERRIDE

usage() {
    echo "Usage: $(basename "$0") <rise.wav> <loop.wav> | --monitors <rise> <loop> | --probe" >&2
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

# One line per connected monitor: card:dev:name:hdmi-index. `aplay -l` names
# an HDMI/DP device after its ELD ("HDMI 0 [G27Q]"); an empty port keeps
# "HDMI n [HDMI n]".
monitor_sinks() {
    if [[ "$MONITORS_OVERRIDE" != "__unset__" ]]; then
        tr ' ' '\n' <<<"$MONITORS_OVERRIDE" | grep -v '^$' || true
        return
    fi
    aplay -l 2>/dev/null |
        sed -nE 's/^card [0-9]+: ([^ ]+) \[[^]]*\], device ([0-9]+): HDMI ([0-9]+) \[(.+)\]$/\1:\2:\4:\3/p' |
        grep -vE ':HDMI [0-9]+:[0-9]+$' || true
}

# One sink's ring: the rise, a `ring_sink` line saying whether it opened,
# then the loop until SIGTERM. The rise lasts a minute, so "opened" means
# aplay is still playing after OPEN_CHECK_SECONDS. A sink that cannot open
# logs and gives up, so one dead monitor never stops the others.
ring_sink() {
    local card="$1" dev="$2" name="$3" rise="$4" loop="$5" device err pid rc=0
    device="plughw:CARD=${card},DEV=${dev}"
    err="$(mktemp)"
    aplay -q -D "$device" "$rise" 2>"$err" &
    pid=$!
    sleep "$OPEN_CHECK_SECONDS"
    if ! kill -0 "$pid" 2>/dev/null; then
        wait "$pid" || rc=$?
    fi
    if [[ $rc -ne 0 ]]; then
        echo "ring_sink sink=$name device=$card,$dev result=error $(tr '\n' ' ' <"$err")"
        rm -f "$err"
        return 1
    fi
    echo "ring_sink sink=$name device=$card,$dev result=ok"
    rm -f "$err"
    wait "$pid" 2>/dev/null || true
    while true; do
        aplay -q -D "$device" "$loop" 2>/dev/null || sleep "$RETRY_SECONDS"
    done
}

# Every monitor in the background, IEC958 unmuted first.
start_monitors() {
    local rise="$1" loop="$2" card dev name index
    while IFS=: read -r card dev name index; do
        [[ -n "$card" ]] || continue
        amixer -q -c "$card" sset "IEC958,${index}" unmute >/dev/null 2>&1 || true
        ring_sink "$card" "$dev" "$name" "$rise" "$loop" &
    done < <(monitor_sinks)
}

# Silence into every monitor; 0 only when each opened and took >= 1.5 s.
# IEC958 is muted for the check and put back the way it was found.
probe() {
    local card dev name index start ms rc err was failed=0 found=0
    while IFS=: read -r card dev name index; do
        [[ -n "$card" ]] || continue
        found=1
        was=unmute
        if amixer -c "$card" sget "IEC958,${index}" 2>/dev/null | grep -q '\[off\]'; then
            was=mute
        fi
        amixer -q -c "$card" sset "IEC958,${index}" mute >/dev/null 2>&1 || true
        start="$(date +%s%N)"
        rc=0
        err="$(aplay -q -D "plughw:CARD=${card},DEV=${dev}" -t raw -f S16_LE -r 48000 \
            -c 2 -d 2 /dev/zero 2>&1)" || rc=$?
        ms=$((($(date +%s%N) - start) / 1000000))
        amixer -q -c "$card" sset "IEC958,${index}" "$was" >/dev/null 2>&1 || true
        if [[ $rc -eq 0 && $ms -ge 1500 ]]; then
            echo "ring_probe sink=$name device=$card,$dev result=ok ms=$ms"
        else
            echo "ring_probe sink=$name device=$card,$dev result=error rc=$rc ms=$ms ${err//$'\n'/ }"
            failed=1
        fi
    done < <(monitor_sinks)
    if [[ $found -eq 0 ]]; then
        echo "ring_probe result=error no connected monitor"
        return 1
    fi
    return "$failed"
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
    if [[ "${1:-}" == "--probe" ]]; then
        probe
        return
    fi
    if [[ "${1:-}" == "--monitors" ]]; then
        [[ $# -eq 3 ]] || usage
        # SIGTERM from the PipeWire path: end every loop, then exit.
        trap 'kill $(jobs -p) 2>/dev/null || true; exit 0' TERM INT
        start_monitors "$2" "$3"
        wait
        return
    fi
    [[ $# -eq 2 ]] || usage
    local rise="$1" loop="$2"
    [[ -r "$rise" && -r "$loop" ]] || {
        echo "Error: cannot read $rise / $loop" >&2
        exit 1
    }
    # The monitor loops die with this script, whatever ends it.
    trap 'kill $(jobs -p) 2>/dev/null || true' EXIT
    start_monitors "$rise" "$loop"
    unmute_all
    local rc=0
    play "$rise" || rc=$?
    [[ $rc -ne 3 ]] || handle_busy "$rise" "$loop"
    [[ $rc -ne 0 ]] || echo "ring_sink sink=speakers device=$CARD,0 result=ok"
    while true; do
        play "$loop" || sleep "$RETRY_SECONDS"
    done
}

main "$@"
