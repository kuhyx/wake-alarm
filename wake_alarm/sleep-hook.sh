#!/bin/bash
# systemd-sleep hook: start the unified morning routine after resume.
#
# Installed to /usr/lib/systemd/system-sleep/wake-alarm.sh by install.sh.
#
# When the PC hibernates (rtcwake -m disk) and resumes the next morning, the
# user session is restored but no morning service is running. This hook starts
# morning-routine.service, which runs the wake alarm first (it owns the
# fullscreen until dismissed) and then the workout screen lock - one coherent
# flow, with the two never fighting for the screen.

if [[ "$1" != "post" ]]; then
    exit 0
fi

logger -t wake-alarm-hook "Woke from sleep (type=$2) - starting morning-routine.service for active sessions"

# Start wake-alarm.service for every logged-in user that has a running session
# bus. Works with systemd >= 219.
while IFS= read -r uid; do
    runtime_dir="/run/user/$uid"
    [[ -d "$runtime_dir" ]] || continue
    username=$(id -nu "$uid" 2>/dev/null) || continue
    logger -t wake-alarm-hook "Starting morning-routine.service for user $username (uid=$uid)"
    XDG_RUNTIME_DIR="$runtime_dir" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=${runtime_dir}/bus" \
    runuser -u "$username" -- \
        systemctl --user start morning-routine.service 2>/dev/null \
    || logger -t wake-alarm-hook "Failed to start morning-routine.service for $username (non-fatal)"
done < <(loginctl list-sessions --no-legend 2>/dev/null | awk '{print $2}' | sort -u)
