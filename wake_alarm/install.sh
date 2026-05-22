#!/bin/bash
# Install the weekend wake alarm systemd user service and sudoers entry.
#
# Usage: bash install.sh
#
# What it does:
#   1. Copies wake-alarm.service to ~/.config/systemd/user/
#   2. Enables and starts the service
#   3. Installs the systemd-sleep hook (restarts alarm after hibernate resume)
#   4. Adds a sudoers entry for passwordless rtcwake
#   5. Installs shutdown wrapper so "shutdown now" also hibernates on alarm nights

set -euo pipefail

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
SERVICE_FILE="$SCRIPT_DIR/wake-alarm.service"
SLEEP_HOOK_SRC="$SCRIPT_DIR/sleep-hook.sh"
SHUTDOWN_WRAPPER_SRC="$SCRIPT_DIR/shutdown-wrapper.sh"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SLEEP_HOOK_DST="/usr/lib/systemd/system-sleep/wake-alarm.sh"
SHUTDOWN_WRAPPER_DST="/usr/local/bin/shutdown"
SUDOERS_FILE="/etc/sudoers.d/wake-alarm"
RTCWAKE_BIN="/usr/sbin/rtcwake"

echo "=== Weekend Wake Alarm Installer ==="

# 0. Install system dependencies
echo "[0/5] Checking system dependencies..."
if ! command -v speaker-test &>/dev/null; then
    echo "  Installing alsa-utils (required for speaker-test)..."
    sudo pacman -S --noconfirm alsa-utils
else
    echo "  alsa-utils already installed"
fi

# 1. Install systemd user service
echo "[1/5] Installing systemd user service..."
mkdir -p "$SYSTEMD_USER_DIR"
cp "$SERVICE_FILE" "$SYSTEMD_USER_DIR/wake-alarm.service"
systemctl --user daemon-reload
echo "  Installed to $SYSTEMD_USER_DIR/wake-alarm.service"

# 2. Enable service
echo "[2/5] Enabling wake-alarm.service..."
systemctl --user enable wake-alarm.service
echo "  Service enabled (will start on next boot)"

# 3. Install systemd-sleep hook (restarts alarm after hibernate resume)
echo "[3/5] Installing systemd-sleep hook..."
sudo cp "$SLEEP_HOOK_SRC" "$SLEEP_HOOK_DST"
sudo chmod 0755 "$SLEEP_HOOK_DST"
echo "  Installed to $SLEEP_HOOK_DST"

# 4. Add sudoers entry for rtcwake (requires root)
echo "[4/5] Setting up sudoers for rtcwake..."
SUDOERS_LINE="$USER ALL=(root) NOPASSWD: $RTCWAKE_BIN"
if [[ -f "$SUDOERS_FILE" ]] && grep -qF "$SUDOERS_LINE" "$SUDOERS_FILE"; then
    echo "  Sudoers entry already exists"
else
    echo "  Adding sudoers entry (requires sudo)..."
    echo "$SUDOERS_LINE" | sudo tee "$SUDOERS_FILE" > /dev/null
    sudo chmod 0440 "$SUDOERS_FILE"
    echo "  Added: $SUDOERS_LINE"
fi

# 5. Install shutdown wrapper (/usr/local/bin/shutdown shadows /usr/bin/shutdown)
echo "[5/5] Installing shutdown wrapper..."
sudo cp "$SHUTDOWN_WRAPPER_SRC" "$SHUTDOWN_WRAPPER_DST"
sudo chmod 0755 "$SHUTDOWN_WRAPPER_DST"
echo "  Installed to $SHUTDOWN_WRAPPER_DST"
echo "  'shutdown now' will now hibernate (not poweroff) on alarm nights."

echo "=== Installation complete ==="
echo "The wake alarm will activate on boot for alarm days (Mon, Fri, Sat, Sun)."
echo "After hibernate resume the sleep hook will restart the alarm service."
echo "To test now: python -m python_pkg.wake_alarm._alarm --demo"
