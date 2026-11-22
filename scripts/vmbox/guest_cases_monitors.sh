#!/bin/bash

# ============================================================================
# wake_alarm vmbox harness — the monitors ring too (2026-11-22). Two fake
# monitors on snd-dummy's extra PCM devices (WAKE_ALARM_MONITORS stands in
# for the ELD names `aplay -l` reads on the PC): each must log its own
# `ring_sink ... result=ok`, a dead one must log an error without stopping
# the others, and --probe must pass on silence. Sourced by guest_cases_v2.sh.
# ============================================================================

# snd-dummy with three PCM devices: 0 = speakers, 1 and 2 = the monitors.
monitors_card() {
    sudo modprobe -r snd-dummy >/dev/null 2>&1 || true
    sudo modprobe snd-dummy pcm_devs=3
    sudo udevadm settle
}

case_ring_monitor_sinks() {
    local name="ring-alsa-monitor-sinks" out
    monitors_card
    out="$(sudo WAKE_ALARM_CARD=Dummy WAKE_ALARM_USER="$USER" \
        WAKE_ALARM_MONITORS="Dummy:1:MonA:0 Dummy:2:MonB:1 Nope:0:Dead:2" \
        timeout 5 "$RING_SCRIPT" "$RING_WAV_DIR/ring.wav" "$RING_WAV_DIR/ring_loop.wav" 2>&1)" || true
    if grep -q "ring_sink sink=MonA device=Dummy,1 result=ok" <<<"$out" &&
        grep -q "ring_sink sink=MonB device=Dummy,2 result=ok" <<<"$out" &&
        grep -q "ring_sink sink=Dead device=Nope,0 result=error" <<<"$out"; then
        pass "$name"
    else
        fail "$name" "ring_sink lines: $(grep ring_sink <<<"$out" | tr '\n' '|')"
    fi
}

case_ring_monitor_probe() {
    local name="ring-alsa-monitor-probe" out rc=0
    monitors_card
    out="$(sudo WAKE_ALARM_MONITORS="Dummy:1:MonA:0 Dummy:2:MonB:1" \
        "$RING_SCRIPT" --probe 2>&1)" || rc=$?
    if [[ $rc -eq 0 ]] && [[ "$(grep -c 'ring_probe .*result=ok' <<<"$out")" -eq 2 ]]; then
        pass "$name"
    else
        fail "$name" "rc=$rc: $(tr '\n' '|' <<<"$out")"
    fi
}

run_monitor_cases() {
    case_ring_monitor_sinks
    case_ring_monitor_probe
}
