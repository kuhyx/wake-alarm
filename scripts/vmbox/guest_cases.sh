#!/bin/bash

# ============================================================================
# wake_alarm vmbox harness — the cases that run INSIDE the guest.
#
# Kept as its own file rather than inlined into `vm run` for two reasons: the
# vmbox runner wraps its argument in `sh -c` and chokes on a multi-line
# command, and a real file gets shellcheck like every other script here.
#
# Each case prints "PASS <name>" or "FAIL <name>: <why>" and the script exits
# non-zero if any failed, so the host adjudicates on an exit code rather than
# by reading prose.
# ============================================================================

set -uo pipefail

readonly PY=/usr/bin/python3
FAILURES=0

pass() {
    echo "PASS $1"
}

fail() {
    echo "FAIL $1: $2"
    FAILURES=$((FAILURES + 1))
}

# --- Case: the package installs and imports from SYSTEM python ---------------
# The units run /usr/bin/python directly, never a venv, so this is the check
# that actually matters (CLAUDE.md).
case_imports() {
    local name="imports-from-system-python"
    if "$PY" -c "import wake_alarm, gatelock" 2>/dev/null; then
        pass "$name"
    else
        fail "$name" "wake_alarm or gatelock missing from /usr/bin/python3"
    fi
}

# --- Case: the trigger timer is actually enabled -----------------------------
# install.sh writing the unit file is not the same as systemd running it, and
# a timer that is present but disabled fails silently every morning.
case_units() {
    local name state
    name="trigger-timer-enabled"
    state="$(systemctl --user is-enabled wake-alarm-trigger.timer 2>&1)"
    if [[ "$state" == "enabled" ]]; then
        pass "$name"
    else
        fail "$name" "expected enabled, got '$state'"
    fi
}

# --- Case: the trigger decides without crashing ------------------------------
case_trigger_dry_run() {
    local name="trigger-dry-run"
    if "$PY" -m wake_alarm._trigger --dry-run 2>/dev/null | grep -q "firing"; then
        pass "$name"
    else
        fail "$name" "--dry-run produced no decision line"
    fi
}

main() {
    case "${1:-all}" in
        all)
            case_imports
            case_units
            case_trigger_dry_run
            ;;
        *)
            echo "usage: $0 [all]" >&2
            exit 2
            ;;
    esac

    echo "---"
    if [[ $FAILURES -gt 0 ]]; then
        echo "$FAILURES case(s) failed"
        exit 1
    fi
    # The host greps for this exact string. `vm run` reports the VM's verdict
    # rather than this script's exit code, so an exit status alone would let
    # the gate fail open.
    echo "ALL-CASES-PASSED"
}

main "$@"
