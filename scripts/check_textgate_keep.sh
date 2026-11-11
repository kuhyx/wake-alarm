#!/bin/bash

# ============================================================================
# Fail if `textgate scan` reports any text item not covered by keep.md.
#
# textgate has no path exclusion and its config is a gate control, so the
# repo's deliberate exceptions live in keep.md instead. This script reads the
# "## Scan exceptions" table there (first cell: a backticked file, or a
# directory ending in "/"; second cell: the backticked exact text, or * for
# any text) and prints every scan hit no row covers.
#
# Not wired into pre-commit or CI: adding it there is a gate change.
#
# Usage: scripts/check_textgate_keep.sh        (from anywhere in the repo)
# Exit:  0 all hits kept, 1 unmatched hits, 2 missing tool or keep file.
# Needs: textgate, jq.
# ============================================================================

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
readonly REPO_ROOT
readonly KEEP_FILE="$REPO_ROOT/keep.md"
readonly SECTION="## Scan exceptions"

die() {
    echo "Error: $*" >&2
    exit 2
}

# Print the exception rows of keep.md as "path<TAB>text" (empty text = any).
keep_rows() {
    awk -v section="$SECTION" '/^## /{on = ($0 == section)} on && /^\| `/' "$KEEP_FILE" |
        sed -E 's/^\| `([^`]+)` \| (`([^`]*)`|\*) \|.*$/\1\t\3/'
}

main() {
    command -v textgate >/dev/null || die "textgate not found on PATH"
    command -v jq >/dev/null || die "jq not found on PATH"
    [[ -f "$KEEP_FILE" ]] || die "keep list not found at $KEEP_FILE"

    local rows scan unmatched
    rows="$(keep_rows | jq -R -s 'split("\n") | map(select(length > 0) | split("\t") | {path: .[0], text: (.[1] // "")})')"
    # textgate exits 1 whenever it lists any item, so the exit code alone
    # cannot tell hits from a crash: require 0/1 and a JSON array.
    local rc=0
    scan="$(cd "$REPO_ROOT" && textgate scan --json)" || rc=$?
    ((rc <= 1)) || die "textgate scan failed (exit $rc)"
    jq -e 'type == "array"' <<<"$scan" >/dev/null || die "textgate scan did not print a JSON array"
    unmatched="$(jq -r --argjson rows "$rows" '
        def covered($hit): any($rows[] as $r
            | (if ($r.path | endswith("/")) then ($hit.file | startswith($r.path)) else $hit.file == $r.path end)
              and ($r.text == "" or $r.text == $hit.text); .);
        .[] | select(covered(.) | not) | "\(.file):\(.line)  \(.text | tojson)"
    ' <<<"$scan")"

    if [[ -n "$unmatched" ]]; then
        echo "$unmatched"
        echo "textgate keep: $(wc -l <<<"$unmatched") hit(s) not in keep.md" >&2
        exit 1
    fi
    echo "textgate keep: all $(jq length <<<"$scan") hit(s) covered by keep.md"
}

main "$@"
