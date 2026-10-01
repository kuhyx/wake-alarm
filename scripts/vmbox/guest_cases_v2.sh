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
    case_sudoers
    case_powerkey_dropin
    case_rtc_arm
    case_uninstall
}
