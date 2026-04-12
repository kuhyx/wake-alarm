#!/bin/bash
# Install the weekend wake alarm systemd user service and sudoers entry.
#
# Usage: bash install.sh
#
# What it does:
#   1. Copies wake-alarm.service to ~/.config/systemd/user/
#   2. Enables and starts the service
#   3. Adds a sudoers entry for passwordless rtcwake

set -euo pipefail

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
SERVICE_FILE="$SCRIPT_DIR/wake-alarm.service"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SUDOERS_FILE="/etc/sudoers.d/wake-alarm"
RTCWAKE_BIN="/usr/sbin/rtcwake"

echo "=== Weekend Wake Alarm Installer ==="

# 1. Install systemd user service
echo "[1/3] Installing systemd user service..."
mkdir -p "$SYSTEMD_USER_DIR"
cp "$SERVICE_FILE" "$SYSTEMD_USER_DIR/wake-alarm.service"
systemctl --user daemon-reload
echo "  Installed to $SYSTEMD_USER_DIR/wake-alarm.service"

# 2. Enable service
echo "[2/3] Enabling wake-alarm.service..."
systemctl --user enable wake-alarm.service
echo "  Service enabled (will start on next boot)"

# 3. Add sudoers entry for rtcwake (requires root)
echo "[3/3] Setting up sudoers for rtcwake..."
SUDOERS_LINE="$USER ALL=(root) NOPASSWD: $RTCWAKE_BIN"
if [[ -f "$SUDOERS_FILE" ]] && grep -qF "$SUDOERS_LINE" "$SUDOERS_FILE"; then
    echo "  Sudoers entry already exists"
else
    echo "  Adding sudoers entry (requires sudo)..."
    echo "$SUDOERS_LINE" | sudo tee "$SUDOERS_FILE" > /dev/null
    sudo chmod 0440 "$SUDOERS_FILE"
    echo "  Added: $SUDOERS_LINE"
fi

echo ""
echo "=== Installation complete ==="
echo "The wake alarm will activate on boot for alarm days (Mon, Fri, Sat, Sun)."
echo "To test now: python -m python_pkg.wake_alarm._alarm --demo"
