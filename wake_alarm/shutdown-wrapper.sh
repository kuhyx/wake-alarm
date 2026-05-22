#!/bin/bash
# Wrapper for /usr/bin/shutdown that redirects to rtcwake -m disk on alarm
# nights (Mon, Fri, Sat, Sun by tomorrow's day-of-week). This ensures that
# both the automated systemd timer AND manual "shutdown now" hibernate
# correctly so the PC wakes for the morning alarm.
#
# Install to /usr/local/bin/shutdown (takes priority over /usr/bin/shutdown
# because /usr/local/bin appears first in PATH).

set -euo pipefail

REAL_SHUTDOWN=/usr/bin/shutdown
RTCWAKE=/usr/sbin/rtcwake
WAKE_AFTER_HOURS=8  # Must match WAKE_AFTER_HOURS in python_pkg/wake_alarm/_constants.py

# Pass through reboots and cancel commands unchanged.
for arg in "$@"; do
    case "$arg" in
        -r|--reboot|-c|--cancel)
            exec "$REAL_SHUTDOWN" "$@"
            ;;
    esac
done

# Check if tomorrow is an alarm day (Mon=1, Fri=5, Sat=6, Sun=7 in date +%u).
tomorrow_dow=$(date -d "tomorrow" +%u)
case "$tomorrow_dow" in
    1|5|6|7)
        wake_epoch=$(( $(printf '%(%s)T' -1) + WAKE_AFTER_HOURS * 3600 ))
        logger -t shutdown-wrapper \
            "Tomorrow is alarm day (dow=$tomorrow_dow) — hibernating, RTC wake at epoch $wake_epoch"
        sudo "$RTCWAKE" -m no -t "$wake_epoch"
        exec /usr/bin/systemctl hibernate
        ;;
    *)
        exec "$REAL_SHUTDOWN" "$@"
        ;;
esac
