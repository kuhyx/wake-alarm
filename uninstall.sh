#!/bin/bash
# Remove the PC's waking machinery.
#
# Usage:
#   bash uninstall.sh                 # remove everything this repo installed
#   bash uninstall.sh --retired-only  # remove only the retired waking pieces
#
# WHY THIS SCRIPT EXISTS, AND WHY `rm -rf` ON THE REPO IS NOT ENOUGH:
# `/usr/local/bin/shutdown` is root-owned and shadows `/usr/bin/shutdown` via
# PATH order. Deleting the repo does NOT remove it, and with the alarm cache
# gone it falls through to `sudo rtcwake ... ; exec systemctl hibernate` --
# so `shutdown now` would silently stop being a poweroff, every day, forever.
#
# `/etc/sudoers.d/wake-alarm` is deliberately LEFT IN PLACE even by a full
# uninstall: screen-locker's own _wake_alarm.py:_schedule_rtcwake still shells
# out to `sudo rtcwake`, and removing the entry here would break a live feature
# in another repo with no error message anywhere.

set -euo pipefail

readonly SLEEP_HOOK_DST="/usr/lib/systemd/system-sleep/wake-alarm.sh"
readonly SHUTDOWN_WRAPPER_DST="/usr/local/bin/shutdown"
readonly SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
# Enforcement v2 (DOCS-wake-enforcement.md): user units, then root pieces.
readonly V2_UNITS=(wake-alarm-fallback wake-alarm-rtc wake-alarm-audit)
readonly ALSA_UNIT="wake-alarm-ring-alsa.service"
readonly ROOT_FILES=(
    "/etc/systemd/system/$ALSA_UNIT"
    "/usr/local/lib/wake-alarm/ring_alsa.sh"
    "/usr/local/share/wake-alarm/ring.wav"
    "/usr/local/share/wake-alarm/ring_loop.wav"
)
readonly POWERKEY_DST="/etc/systemd/logind.conf.d/wake-alarm-powerkey.conf"

RETIRED_ONLY=0

usage() {
    echo "Usage: $(basename "$0") [--retired-only]"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --retired-only) RETIRED_ONLY=1; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

if [[ -n "${SUDO_USER:-}" || $EUID -eq 0 ]]; then
    echo "Error: do not run this script with sudo." >&2
    echo "Run it as your normal user:  bash $0" >&2
    exit 1
fi

remove_retired() {
    # The shutdown wrapper. Checked by content, not just existence, so this
    # never deletes an unrelated /usr/local/bin/shutdown someone else put there.
    if [[ -f "$SHUTDOWN_WRAPPER_DST" ]] \
        && grep -q 'wake-alarm\|rtcwake' "$SHUTDOWN_WRAPPER_DST"; then
        echo "  Removing $SHUTDOWN_WRAPPER_DST (restores real /usr/bin/shutdown)"
        sudo rm -f "$SHUTDOWN_WRAPPER_DST"
    else
        echo "  $SHUTDOWN_WRAPPER_DST: not ours or already gone"
    fi

    if [[ -f "$SLEEP_HOOK_DST" ]]; then
        echo "  Removing $SLEEP_HOOK_DST"
        sudo rm -f "$SLEEP_HOOK_DST"
    else
        echo "  $SLEEP_HOOK_DST: already gone"
    fi

    # wake-alarm.service is gone from the repo; clear any stale installed copy
    # and its enable symlink.
    if [[ -f "$SYSTEMD_USER_DIR/wake-alarm.service" ]]; then
        echo "  Removing stale wake-alarm.service"
        systemctl --user disable wake-alarm.service >/dev/null 2>&1 || true
        rm -f "$SYSTEMD_USER_DIR/wake-alarm.service"
    else
        echo "  wake-alarm.service: already gone"
    fi
}

remove_trigger() {
    echo "  Disabling the trigger timer"
    systemctl --user disable --now wake-alarm-trigger.timer >/dev/null 2>&1 || true
    systemctl --user disable --now wake-alarm-session.timer >/dev/null 2>&1 || true
    rm -f "$SYSTEMD_USER_DIR/wake-alarm-trigger.service" \
          "$SYSTEMD_USER_DIR/wake-alarm-trigger.timer" \
          "$SYSTEMD_USER_DIR/wake-alarm-session.service" \
          "$SYSTEMD_USER_DIR/wake-alarm-session.timer"
}

remove_enforcement() {
    local unit path
    for unit in "${V2_UNITS[@]}"; do
        systemctl --user disable --now "$unit.timer" >/dev/null 2>&1 || true
        systemctl --user stop "$unit.service" >/dev/null 2>&1 || true
        rm -f "$SYSTEMD_USER_DIR/$unit.service" "$SYSTEMD_USER_DIR/$unit.timer"
    done
    echo "  Fallback, RTC and audit timers removed"

    sudo systemctl stop "$ALSA_UNIT" >/dev/null 2>&1 || true
    for path in "${ROOT_FILES[@]}"; do
        sudo rm -f "$path"
    done
    sudo rmdir /usr/local/lib/wake-alarm /usr/local/share/wake-alarm 2>/dev/null || true
    sudo systemctl daemon-reload
    echo "  $ALSA_UNIT, its script and the ring WAVs removed"

    if sudo test -f "$POWERKEY_DST"; then
        sudo rm -f "$POWERKEY_DST"
        # Reload, NEVER restart: restarting logind kills the graphical session.
        sudo systemctl kill -s HUP systemd-logind
        echo "  Power key back to the logind default"
    fi
    # Disarm a pending stick-day wake, so the PC does not start by itself.
    sudo -n /usr/sbin/rtcwake -m disable >/dev/null 2>&1 || true
}

main() {
    echo "=== Removing the PC's waking machinery ==="
    remove_retired

    if [[ $RETIRED_ONLY -eq 0 ]]; then
        remove_trigger
        remove_enforcement
        echo "  Note: the workout lock no longer starts at the phone's alarm time."
    fi

    systemctl --user daemon-reload

    echo
    echo "Left in place on purpose:"
    echo "  /etc/sudoers.d/wake-alarm — never deleted by an uninstall (AGENTS.md);"
    echo "  its start/stop lines are inert once $ALSA_UNIT is gone."
    echo
    echo "Verify:  command -v shutdown   # expect /usr/bin/shutdown"
}

main "$@"
