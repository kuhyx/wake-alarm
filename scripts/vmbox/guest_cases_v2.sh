#!/bin/bash

# ============================================================================
# wake_alarm vmbox harness — guest cases for wake enforcement v2
# (DOCS-wake-enforcement.md): the fallback/rtc/audit timers, the root ring
# unit, the sudoers merge, the logind power-key drop-in, a real RTC arm, and
# uninstall undoing all of it. Sourced by guest_cases.sh, which owns
# pass/fail/FAILURES and the sentinel.
# ============================================================================

readonly RING_UNIT=/etc/systemd/system/wake-alarm-ring-alsa.service
readonly RING_SCRIPT=/usr/local/lib/wake-alarm/ring_alsa.sh
readonly RING_WAV_DIR=/usr/local/share/wake-alarm
readonly SUDOERS=/etc/sudoers.d/wake-alarm
readonly POWERKEY_DROPIN=/etc/systemd/logind.conf.d/wake-alarm-powerkey.conf
readonly WAKEALARM=/sys/class/rtc/rtc0/wakealarm

# A timer present but disabled fails silently every morning.
case_v2_timers() {
    local timer state
    for timer in wake-alarm-fallback.timer wake-alarm-rtc.timer wake-alarm-audit.timer; do
        state="$(systemctl --user is-enabled "$timer" 2>&1)"
        if [[ "$state" == "enabled" ]]; then
            pass "${timer%.timer}-enabled"
        else
            fail "${timer%.timer}-enabled" "expected enabled, got '$state'"
        fi
    done
}

case_ring_unit_installed() {
    local name="ring-alsa-installed"
    if [[ -f "$RING_UNIT" && -x "$RING_SCRIPT" && -s "$RING_WAV_DIR/ring.wav" &&
        -s "$RING_WAV_DIR/ring_loop.wav" ]]; then
        pass "$name"
    else
        fail "$name" "unit, script or WAVs missing"
    fi
}

# The root ring is what plays during the night lockdown; prove the script
# drives a real ALSA card (snd-dummy here) as root and keeps looping.
case_ring_script_plays() {
    local name="ring-alsa-plays" rc=0
    sudo modprobe snd-dummy >/dev/null 2>&1 || true
    if ! sudo aplay -l 2>/dev/null | grep -q Dummy; then
        fail "$name" "snd-dummy did not load"
        return
    fi
    sudo WAKE_ALARM_CARD=Dummy timeout 4 "$RING_SCRIPT" \
        "$RING_WAV_DIR/ring.wav" "$RING_WAV_DIR/ring_loop.wav" >/dev/null 2>&1 || rc=$?
    # 124 = still playing when timeout killed it: the loop is alive.
    if [[ $rc -eq 124 ]]; then
        pass "$name"
    else
        fail "$name" "expected timeout (124) while looping, got $rc"
    fi
}

# --- card held busy (PipeWire holds it on the real PC) ----------------------
readonly BUSY_REPS=10
readonly BUSY_DIR=/tmp/ring-busy
readonly EVENTS="$HOME/.local/state/wake_alarm/events.jsonl"

# Stub wpctl/pw-play: the guest has no user PipeWire. $1 = "ok" or "broken".
busy_stubs() {
    mkdir -p "$BUSY_DIR/bin"
    printf '#!/bin/sh\nexit 0\n' >"$BUSY_DIR/bin/wpctl"
    if [[ "$1" == ok ]]; then
        printf '#!/bin/sh\nexec sleep 30\n' >"$BUSY_DIR/bin/pw-play"
    else
        printf '#!/bin/sh\nexit 1\n' >"$BUSY_DIR/bin/pw-play"
    fi
    chmod +x "$BUSY_DIR/bin/"*
}

# Hold the Dummy card's only playback substream, ignoring TERM.
busy_hold() {
    sudo modprobe -r snd-dummy >/dev/null 2>&1 || true
    sudo modprobe snd-dummy pcm_substreams=1
    setsid bash -c 'trap "" TERM; exec aplay -q -D plughw:CARD=Dummy,DEV=0 /dev/zero -f S16_LE -r 8000 -c 1' \
        >/dev/null 2>&1 &
    sleep 1
}

busy_release() {
    sudo pkill -KILL -x aplay >/dev/null 2>&1 || true
}

# A ring_backend event in the user's log carrying $1 (started true/false).
busy_event() {
    grep '"event": "ring_backend"' "$EVENTS" 2>/dev/null | grep -q "$1"
}

# Run the ring script against the held card; $1 = seconds to let it run.
busy_run() {
    sudo WAKE_ALARM_CARD=Dummy WAKE_ALARM_USER="$USER" PATH="$BUSY_DIR/bin:$PATH" \
        timeout "$1" "$RING_SCRIPT" "$RING_WAV_DIR/ring.wav" "$RING_WAV_DIR/ring_loop.wav" 2>&1
}

# The first busy open hands the ring to PipeWire, N times over, with the
# holder alive and ignoring TERM (so a kill-first design would fail here).
case_ring_busy_fallback() {
    local name="ring-alsa-busy-fallback" i ok=0 out
    busy_stubs ok
    busy_hold
    for ((i = 1; i <= BUSY_REPS; i++)); do
        : >"$EVENTS" 2>/dev/null || true
        out="$(busy_run 4)" || true
        if grep -q '^fallback-started' <<<"$out" &&
            ! grep -q 'kill-holder' <<<"$out" &&
            busy_event '"started": true'; then
            ok=$((ok + 1))
        fi
    done
    busy_release
    if [[ $ok -eq $BUSY_REPS ]]; then
        pass "$name"
    else
        fail "$name" "$ok of $BUSY_REPS repetitions fell back on the first busy open"
    fi
}

# Holder present AND fallback broken: never a silent success.
case_ring_busy_fails_loudly() {
    local name="ring-alsa-busy-fails-loudly" out rc=0
    busy_stubs broken
    busy_hold
    : >"$EVENTS" 2>/dev/null || true
    out="$(busy_run 15)" || rc=$?
    busy_release
    if [[ $rc -ne 0 && $rc -ne 124 ]] && grep -q 'kill-holder' <<<"$out" &&
        busy_event '"started": false'; then
        pass "$name"
    else
        fail "$name" "rc=$rc, expected non-zero exit, kill-holder and a FAILED event"
    fi
}

case_sudoers() {
    local name="sudoers-merged"
    if ! sudo visudo -cf "$SUDOERS" >/dev/null 2>&1; then
        fail "$name" "visudo rejects $SUDOERS"
        return
    fi
    if sudo grep -q "systemctl start wake-alarm-ring-alsa.service" "$SUDOERS" &&
        sudo grep -q "systemctl stop wake-alarm-ring-alsa.service" "$SUDOERS" &&
        sudo grep -q "/usr/sbin/rtcwake" "$SUDOERS"; then
        pass "$name"
    else
        fail "$name" "start/stop/rtcwake lines missing"
    fi
}

case_powerkey_dropin() {
    local name="powerkey-dropin-hibernate"
    if grep -qx "HandlePowerKey=hibernate" "$POWERKEY_DROPIN" 2>/dev/null; then
        pass "$name"
    else
        fail "$name" "drop-in missing in default (hibernate) mode"
    fi
}

# A real arm through the production sudo path; the guest has no Firebase,
# so the alarm falls back to 08:00 and the next Tue/Wed/Thu is the target.
case_rtc_arm() {
    local name="rtc-arm-real" armed
    # A Monday evening, so the next morning is a stick day (Tuesday). The
    # guest is disposable; its clock is fair game.
    sudo timedatectl set-ntp false >/dev/null 2>&1 || true
    sudo date -s "next monday 21:00" >/dev/null
    # Move the RTC too: rtcwake arms relative to it, and sysfs reports it.
    sudo hwclock --systohc --utc >/dev/null 2>&1
    "$PY" -m wake_alarm._rtc --arm 2>&1 | sed 's/^/    rtc: /' || true
    armed="$(cat "$WAKEALARM" 2>/dev/null)"
    if [[ -n "$armed" ]] && "$PY" -m wake_alarm._rtc --show 2>/dev/null | grep -q "$armed"; then
        pass "$name"
    else
        fail "$name" "wakealarm='${armed}' not reported by --show"
    fi
}

# Last: uninstall must remove everything except the sudoers file.
case_uninstall() {
    local name="uninstall-cleans" leftovers=()
    (cd ~/wake-alarm && bash uninstall.sh >/dev/null 2>&1) || true
    [[ -e "$RING_UNIT" ]] && leftovers+=("$RING_UNIT")
    [[ -e "$RING_SCRIPT" ]] && leftovers+=("$RING_SCRIPT")
    [[ -e "$POWERKEY_DROPIN" ]] && leftovers+=("$POWERKEY_DROPIN")
    [[ -n "$(cat "$WAKEALARM" 2>/dev/null)" ]] && leftovers+=("rtc alarm")
    systemctl --user is-enabled wake-alarm-fallback.timer >/dev/null 2>&1 &&
        leftovers+=("fallback timer")
    # /etc/sudoers.d is root-only (0750): stat it as root.
    sudo test -e "$SUDOERS" || leftovers+=("sudoers REMOVED (must stay)")
    if [[ ${#leftovers[@]} -eq 0 ]]; then
        pass "$name"
    else
        fail "$name" "${leftovers[*]}"
    fi
}

run_v2_cases() {
    case_v2_timers
    case_ring_unit_installed
    case_ring_script_plays
    case_ring_busy_fallback
    case_ring_busy_fails_loudly
    case_sudoers
    case_powerkey_dropin
    case_rtc_arm
    case_uninstall
}
