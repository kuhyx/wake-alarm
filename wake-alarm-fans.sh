#!/bin/bash
# Control ALL NCT pwm fan channels for the wake alarm.
#
# Usage:
#   wake-alarm-fans.sh max       — ramp every pwm[1-9] channel to 100%
#   wake-alarm-fans.sh restore   — restore the state captured by the last `max`
#
# Must be run as root (installed in /etc/sudoers.d/wake-alarm via install.sh).
# Safe: fans are designed to run at max speed indefinitely.
#
# State is stored at $STATE_FILE so `restore` doesn't need any arguments.

set -euo pipefail

STATE_FILE="/run/wake-alarm-fans.state"

# Locate the hwmon directory for any NCT Super I/O fan controller.
HWMON=""
for name_file in /sys/class/hwmon/hwmon*/name; do
    [[ -f "$name_file" ]] || continue
    chip=$(cat "$name_file")
    case "$chip" in
        nct6775|nct6779|nct6791|nct6792|nct6793|nct6795|nct6796|nct6797|nct6798|nct6799)
            HWMON=$(dirname "$name_file")
            break
            ;;
    esac
done

if [[ -z "$HWMON" ]]; then
    # Not an error — hardware without this chip just skips fan control.
    exit 0
fi

case "${1:-}" in
    max)
        : > "$STATE_FILE"
        for pwm in "$HWMON"/pwm[0-9]; do
            [[ -w "$pwm" ]] || continue
            enable="${pwm}_enable"
            [[ -w "$enable" ]] || continue
            old_pwm=$(cat "$pwm")
            old_enable=$(cat "$enable")
            printf '%s %s %s\n' "$pwm" "$old_enable" "$old_pwm" >> "$STATE_FILE"
            echo 1   > "$enable"   # Switch to manual mode.
            echo 255 > "$pwm"      # 255/255 = 100% speed.
        done
        ;;
    restore)
        [[ -f "$STATE_FILE" ]] || exit 0
        while read -r pwm old_enable old_pwm; do
            [[ -w "$pwm" && -w "${pwm}_enable" ]] || continue
            # Restore pwm value first, then restore the control mode.
            echo "$old_pwm"    > "$pwm"
            echo "$old_enable" > "${pwm}_enable"
        done < "$STATE_FILE"
        rm -f "$STATE_FILE"
        ;;
    *)
        echo "Usage: $0 max | $0 restore" >&2
        exit 1
        ;;
esac
