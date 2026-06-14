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
#   6. Installs fan-control script so alarm can max fans on wake
#   7. Installs python-kasa (AUR) so the alarm can toggle a Tapo P110 smart plug

set -euo pipefail

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
SERVICE_FILE="$SCRIPT_DIR/wake-alarm.service"
SLEEP_HOOK_SRC="$SCRIPT_DIR/sleep-hook.sh"
SHUTDOWN_WRAPPER_SRC="$SCRIPT_DIR/shutdown-wrapper.sh"
FANS_SCRIPT_SRC="$SCRIPT_DIR/wake-alarm-fans.sh"
FANS_SCRIPT_DST="/usr/local/bin/wake-alarm-fans.sh"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SLEEP_HOOK_DST="/usr/lib/systemd/system-sleep/wake-alarm.sh"
SHUTDOWN_WRAPPER_DST="/usr/local/bin/shutdown"
SUDOERS_FILE="/etc/sudoers.d/wake-alarm"
RTCWAKE_BIN="/usr/sbin/rtcwake"

echo "=== Weekend Wake Alarm Installer ==="

# 0. Install system dependencies
echo "[0/7] Checking system dependencies..."
if ! command -v speaker-test &>/dev/null; then
    echo "  Installing alsa-utils (required for speaker-test)..."
    sudo pacman -S --noconfirm alsa-utils
else
    echo "  alsa-utils already installed"
fi

# 1. Install systemd user service
echo "[1/7] Installing systemd user service..."
mkdir -p "$SYSTEMD_USER_DIR"
cp "$SERVICE_FILE" "$SYSTEMD_USER_DIR/wake-alarm.service"
systemctl --user daemon-reload
echo "  Installed to $SYSTEMD_USER_DIR/wake-alarm.service"

# 2. Enable service
echo "[2/7] Enabling wake-alarm.service..."
systemctl --user enable wake-alarm.service
echo "  Service enabled (will start on next boot)"

# 3. Install systemd-sleep hook (restarts alarm after hibernate resume)
echo "[3/7] Installing systemd-sleep hook..."
sudo cp "$SLEEP_HOOK_SRC" "$SLEEP_HOOK_DST"
sudo chmod 0755 "$SLEEP_HOOK_DST"
echo "  Installed to $SLEEP_HOOK_DST"

# 4. Add sudoers entry for rtcwake (requires root)
echo "[4/7] Setting up sudoers for rtcwake..."
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
echo "[5/7] Installing shutdown wrapper..."
sudo cp "$SHUTDOWN_WRAPPER_SRC" "$SHUTDOWN_WRAPPER_DST"
sudo chmod 0755 "$SHUTDOWN_WRAPPER_DST"
echo "  Installed to $SHUTDOWN_WRAPPER_DST"
echo "  'shutdown now' will now hibernate (not poweroff) on alarm nights."

# 6. Install fan-control script and its sudoers entry
echo "[6/7] Installing fan-control script..."
sudo cp "$FANS_SCRIPT_SRC" "$FANS_SCRIPT_DST"
sudo chmod 0755 "$FANS_SCRIPT_DST"
FANS_SUDOERS_LINE="$USER ALL=(root) NOPASSWD: $FANS_SCRIPT_DST"
if [[ -f "$SUDOERS_FILE" ]] && grep -qF "$FANS_SUDOERS_LINE" "$SUDOERS_FILE"; then
    echo "  Fan sudoers entry already exists"
else
    # Append to existing file (or create)
    echo "$FANS_SUDOERS_LINE" | sudo tee -a "$SUDOERS_FILE" > /dev/null
    sudo chmod 0440 "$SUDOERS_FILE"
    echo "  Added fan sudoers entry"
fi

# 7. Install python-kasa (AUR) for TP-Link Tapo P110 smart-plug control
echo "[7/8] Installing python-kasa (AUR)..."
if python -c 'import kasa' 2>/dev/null; then
    echo "  python-kasa already installed"
elif command -v yay &>/dev/null; then
    yay -S --noconfirm --needed python-kasa
else
    echo "  WARNING: yay not found; install python-kasa manually for smart-plug support" >&2
fi
if [[ ! -f "$HOME/.config/wake_alarm/tapo.json" ]]; then
    echo "  NOTE: ~/.config/wake_alarm/tapo.json not found — smart-plug control is disabled."
    echo "        Create it (mode 0600) with keys: host, email, password."
fi

# 8. Install ddcutil for DDC/CI monitor power control
# ddcutil lets the alarm force the G27Q on via DDC/CI even when the monitor
# was physically powered off (power button), bypassing DPMS limitations.
echo "[8/8] Installing ddcutil (DDC/CI monitor power control)..."
if command -v ddcutil &>/dev/null; then
    echo "  ddcutil already installed"
else
    sudo pacman -S --noconfirm ddcutil
    echo "  ddcutil installed"
fi
# ddcutil needs access to /dev/i2c-* — add user to i2c group if it exists.
if getent group i2c &>/dev/null; then
    if ! id -nG "$USER" | grep -qw i2c; then
        sudo usermod -aG i2c "$USER"
        echo "  Added $USER to i2c group (re-login required for group to take effect)"
    else
        echo "  $USER already in i2c group"
    fi
else
    echo "  i2c group not found — ddcutil will run via sudo"
fi

echo "=== Installation complete ==="
echo "The wake alarm will activate on boot for alarm days (Mon, Fri, Sat, Sun)."
echo "After hibernate resume the sleep hook will restart the alarm service."
echo "Fans will ramp to 100% while the alarm is active, then restore automatically."
echo "To test now: python -m python_pkg.wake_alarm._alarm --demo"
