#!/bin/bash
# Control CPU/case fan speed for the wake alarm.
#
# Usage:
#   wake-alarm-fans.sh max                       — ramp all NCT fans to 100%
#   wake-alarm-fans.sh restore <enable> <pwm>    — restore saved values
#
# Must be run as root (installed in /etc/sudoers.d/wake-alarm via install.sh).
# Safe: fans are designed to run at max speed indefinitely.

set -euo pipefail

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

PWM_PATH="$HWMON/pwm1"
ENABLE_PATH="$HWMON/pwm1_enable"

case "${1:-}" in
    max)
        echo 1   > "$ENABLE_PATH"   # Switch to manual mode
        echo 255 > "$PWM_PATH"      # 255/255 = 100% speed
        ;;
    restore)
        if [[ $# -ne 3 ]]; then
            echo "Usage: $0 restore <old_enable> <old_pwm>" >&2
            exit 1
        fi
        # Restore pwm value first, then restore the control mode.
        echo "${3}" > "$PWM_PATH"
        echo "${2}" > "$ENABLE_PATH"
        ;;
    *)
        echo "Usage: $0 max | $0 restore <old_enable> <old_pwm>" >&2
        exit 1
        ;;
esac
