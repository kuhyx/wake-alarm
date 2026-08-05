#!/bin/bash
# Install the weekend wake alarm systemd user service and sudoers entry.
#
# Usage: bash install.sh
#
# What it does:
#   1. Installs wake_alarm + dependencies for /usr/bin/python
#   2. Installs system dependencies (alsa-utils, ddcutil)
#   3. Installs the systemd user units and enables the per-minute trigger timer
#      (which fires the alarm at the time the phone synced)
#   4. Installs the systemd-sleep hook (restarts alarm after hibernate resume)
#   5. Adds a sudoers entry for passwordless rtcwake
#   6. Installs shutdown wrapper so "shutdown now" also hibernates on alarm nights
#   7. Installs fan-control script so alarm can max fans on wake
#   8. Installs python-kasa (AUR) so the alarm can toggle a Tapo P110 smart plug
#   9. Installs ddcutil and grants /dev/i2c-* access for DDC/CI monitor control

set -euo pipefail

# Refuse to run under sudo. This script must run as the logged-in user: it
# installs *user* systemd units and calls `sudo` itself for the few root-owned
# pieces. Under sudo, XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS are stripped,
# so `systemctl --user` fails at step 3 and every later step -- including the
# shutdown wrapper at step 6 -- is silently skipped while the earlier pip output
# still looks like success. It also runs pip as root, which leaves root-owned
# files in ~/.cache/pip. Failing loudly here beats a half-finished install.
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
SERVICE_FILE="$SCRIPT_DIR/wake-alarm.service"
TRIGGER_SERVICE_SRC="$SCRIPT_DIR/wake-alarm-trigger.service"
TRIGGER_TIMER_SRC="$SCRIPT_DIR/wake-alarm-trigger.timer"
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

# 1. Install this package + its dependencies into system Python -------------
echo "[1/9] Installing wake_alarm + dependencies for /usr/bin/python..."
/usr/bin/python3 -m pip install --user --break-system-packages -e "$REPO_DIR"
echo "  Installed. Verifying import..."
/usr/bin/python3 -c "import wake_alarm; import gatelock" \
    && echo "  wake_alarm and gatelock import cleanly from the system interpreter."

# 2. Install system dependencies
echo "[2/9] Checking system dependencies..."
if ! command -v speaker-test &>/dev/null; then
    echo "  Installing alsa-utils (required for speaker-test)..."
    sudo pacman -S --noconfirm alsa-utils
else
    echo "  alsa-utils already installed"
fi

# 3. Install systemd user units (alarm + the trigger timer that fires it)
echo "[3/9] Installing systemd user units..."
mkdir -p "$SYSTEMD_USER_DIR"
cp "$SERVICE_FILE" "$SYSTEMD_USER_DIR/wake-alarm.service"
cp "$TRIGGER_SERVICE_SRC" "$SYSTEMD_USER_DIR/wake-alarm-trigger.service"
cp "$TRIGGER_TIMER_SRC" "$SYSTEMD_USER_DIR/wake-alarm-trigger.timer"
systemctl --user daemon-reload
echo "  Installed wake-alarm.service, wake-alarm-trigger.{service,timer}"

# wake-alarm.service must NOT auto-start: the PC is always on, so
# graphical-session.target is reached on every login and the alarm has no time
# gate — it would fire at login time. The timer owns firing (via
# morning-routine.service). Both guards matter under `set -euo pipefail`:
# a unit with no [Install] can't be enabled, and disabling a never-enabled unit
# can also return non-zero.
systemctl --user disable wake-alarm.service 2>/dev/null || true
echo "  wake-alarm.service left disabled (started only by the trigger)"

systemctl --user enable --now wake-alarm-trigger.timer
echo "  Trigger timer enabled and started (ticks once a minute)"

# 4. Install systemd-sleep hook (restarts alarm after hibernate resume)
echo "[4/9] Installing systemd-sleep hook..."
sudo cp "$SLEEP_HOOK_SRC" "$SLEEP_HOOK_DST"
sudo chmod 0755 "$SLEEP_HOOK_DST"
echo "  Installed to $SLEEP_HOOK_DST"

# 5. Add sudoers entry for rtcwake (requires root)
echo "[5/9] Setting up sudoers for rtcwake..."
SUDOERS_LINE="$USER ALL=(root) NOPASSWD: $RTCWAKE_BIN"
if [[ -f "$SUDOERS_FILE" ]] && grep -qF "$SUDOERS_LINE" "$SUDOERS_FILE"; then
    echo "  Sudoers entry already exists"
else
    echo "  Adding sudoers entry (requires sudo)..."
    echo "$SUDOERS_LINE" | sudo tee "$SUDOERS_FILE" > /dev/null
    sudo chmod 0440 "$SUDOERS_FILE"
    echo "  Added: $SUDOERS_LINE"
fi

# 6. Install shutdown wrapper (/usr/local/bin/shutdown shadows /usr/bin/shutdown)
echo "[6/9] Installing shutdown wrapper..."
sudo cp "$SHUTDOWN_WRAPPER_SRC" "$SHUTDOWN_WRAPPER_DST"
sudo chmod 0755 "$SHUTDOWN_WRAPPER_DST"
echo "  Installed to $SHUTDOWN_WRAPPER_DST"
echo "  'shutdown now' will now hibernate (not poweroff) on alarm nights."

# 7. Install fan-control script and its sudoers entry
echo "[7/9] Installing fan-control script..."
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

# 8. Install python-kasa (AUR) for TP-Link Tapo P110 smart-plug control
echo "[8/9] Installing python-kasa (AUR)..."
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

# 9. Install ddcutil for DDC/CI monitor power control
# ddcutil lets the alarm force the G27Q on via DDC/CI even when the monitor
# was physically powered off (power button), bypassing DPMS limitations.
echo "[9/9] Installing ddcutil (DDC/CI monitor power control)..."
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
echo "The trigger timer ticks once a minute and fires the alarm at the time"
echo "the phone last synced (needs ~/.config/wake_alarm/sync.json with a"
echo "repo-scoped GitHub token — see MIGRATION.md)."
echo "Check what it resolves right now: python -m wake_alarm._sync --show"
echo "If the PC is powered down instead, the shutdown wrapper hibernates with"
echo "rtcwake set to the same alarm, and the sleep hook runs it on resume."
echo "Fans will ramp to 100% while the alarm is active, then restore automatically."
echo "To test now: python -m wake_alarm._alarm --demo"
