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
# shellcheck source=guest_cases_v2.sh source-path=SCRIPTDIR
source "$(dirname "$(readlink -f "$0")")/guest_cases_v2.sh"

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
    local timer state
    for timer in wake-alarm-trigger.timer wake-alarm-session.timer; do
        state="$(systemctl --user is-enabled "$timer" 2>&1)"
        if [[ "$state" == "enabled" ]]; then
            pass "${timer%.timer}-enabled"
        else
            fail "${timer%.timer}-enabled" "expected enabled, got '$state'"
        fi
    done
}

# --- Case: the session refresh runs without a backend ------------------------
# The guest has no Firebase config, so --refresh must degrade to "no verified
# morning session" (exit 1) rather than crash: that is what an unconfigured
# machine's timer does every two minutes.
case_session_refresh() {
    local name="session-refresh-degrades" output
    # Exit 1 is the expected verdict here ("nothing verifiable"), so capture
    # first: piped straight into grep, pipefail would fail the case on it.
    output="$("$PY" -m wake_alarm._session --refresh 2>/dev/null || true)"
    if grep -q "no verified" <<<"$output"; then
        pass "$name"
    else
        fail "$name" "--refresh did not degrade cleanly"
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
            case_session_refresh
            run_v2_cases
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
