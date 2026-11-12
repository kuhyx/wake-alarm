#!/bin/bash

# ============================================================================
# Cross-language gate for the free-day pool.
#
# phone_app/lib/services/free_day_pool.dart reimplements the rules that
# ~/src/utils/freedays (Python) owns. Two implementations of one policy drift,
# and a Dart-only test cannot see it: it is self-consistent with the port.
# This writes a pool through the Dart rules and reads it back through the
# Python ones, and fails on any disagreement about what is free, what is
# spent and how many days are left.
#
# Requires the freedays venv that install.sh in ~/src/utils/freedays creates.
#
# Usage: scripts/free_days_interop/check.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
readonly SCRIPT_DIR REPO_DIR
# shellcheck source=../pinned_flutter.sh
source "$REPO_DIR/scripts/pinned_flutter.sh"
readonly FREEDAYS_PYTHON="${FREEDAYS_PYTHON:-$HOME/.local/share/freedays/venv/bin/python}"

TEMP_DIR=""
cleanup() {
    if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

validate_requirements() {
    if [[ ! -x "$FREEDAYS_PYTHON" ]]; then
        echo "Error: no freedays venv at $FREEDAYS_PYTHON (run ~/src/utils/freedays/install.sh)" >&2
        exit 1
    fi
    command -v flutter >/dev/null || { echo "Error: flutter not on PATH" >&2; exit 1; }
}

main() {
    use_pinned_flutter "$REPO_DIR"
    validate_requirements
    TEMP_DIR="$(mktemp -d)"
    local pool="$TEMP_DIR/free_days.json"

    echo "== free-day interop: Dart writes =="
    (
        cd "$REPO_DIR/phone_app"
        FREE_DAYS_INTEROP_OUT="$pool" flutter test test/free_day_interop_writer_test.dart \
            | tail -1
    )
    [[ -s "$pool" ]] || { echo "Error: Dart wrote no fixture" >&2; exit 1; }

    echo "== free-day interop: Python reads =="
    "$FREEDAYS_PYTHON" "$SCRIPT_DIR/verify.py" "$pool"
}

main "$@"
