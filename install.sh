#!/bin/bash
# Install the wake-alarm trigger timer.
#
# Usage: bash install.sh
#
# The PC no longer wakes anyone -- the phone does. All this installs is the
# per-minute trigger that starts morning-routine.service (and therefore the
# workout lock) at the time the phone last synced.
#
# What it does:
#   1. Installs wake_alarm + dependencies for /usr/bin/python
#   2. Installs the systemd user units and enables the per-minute trigger timer
#   3. Removes the retired waking machinery from earlier installs
#
# Deliberately NOT done any more, and why:
#   - no shutdown wrapper, no rtcwake, no sleep hook: the PC does not wake you
#   - the /etc/sudoers.d/wake-alarm entry is left ALONE. screen-locker's own
#     _wake_alarm.py still shells out to `sudo rtcwake`, so removing it here
#     would silently break a live feature in another repo.

set -euo pipefail

# Refuse to run under sudo. This script must run as the logged-in user: it
# installs *user* systemd units and calls `sudo` itself for the few root-owned
# pieces. Under sudo, XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS are stripped,
# so `systemctl --user` fails and later steps are silently skipped while the
# earlier pip output still looks like success. It also runs pip as root, which
# leaves root-owned files in ~/.cache/pip. Failing loudly beats half-finishing.
if [[ -n "${SUDO_USER:-}" || $EUID -eq 0 ]]; then
    echo "Error: do not run this script with sudo." >&2
    echo "Run it as your normal user:  bash $0" >&2
    echo "It will prompt for sudo itself where root is actually needed." >&2
    exit 1
fi

# Split declare/assign so the command-substitution exit code is not masked (SC2155).
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
readonly SCRIPT_DIR
readonly REPO_DIR="$SCRIPT_DIR"
readonly TRIGGER_SERVICE_SRC="$SCRIPT_DIR/wake-alarm-trigger.service"
readonly TRIGGER_TIMER_SRC="$SCRIPT_DIR/wake-alarm-trigger.timer"
readonly SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

echo "=== Wake Alarm Trigger Installer ==="

echo "[1/3] Installing wake_alarm for /usr/bin/python..."
# Editable, and from this clone: a later `git pull` here then updates the
# running production code with no reinstall. A non-editable snapshot taken
# from a scratch directory silently stops tracking this repo.
/usr/bin/python3 -m pip install --user --break-system-packages -e "$REPO_DIR"
echo "  Installed. Verifying import..."
/usr/bin/python3 -c "import wake_alarm; import gatelock"
echo "  wake_alarm and gatelock import under /usr/bin/python."

echo "[2/3] Installing systemd user units..."
mkdir -p "$SYSTEMD_USER_DIR"
cp "$TRIGGER_SERVICE_SRC" "$TRIGGER_TIMER_SRC" "$SYSTEMD_USER_DIR/"
systemctl --user daemon-reload
systemctl --user enable --now wake-alarm-trigger.timer
echo "  Trigger timer enabled and started (ticks once a minute)."

echo "[3/3] Removing retired waking machinery from earlier installs..."
bash "$SCRIPT_DIR/uninstall.sh" --retired-only
echo

echo "=== Installation complete ==="
echo "The timer ticks once a minute and starts morning-routine.service at the"
echo "time the phone last synced."
echo "Check what it resolves right now:  python -m wake_alarm._sync --show"
echo "Check what the next tick would do:  python -m wake_alarm._trigger --dry-run"
echo "Watch it live:  journalctl --user -fu wake-alarm-trigger.service"
