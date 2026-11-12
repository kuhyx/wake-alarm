#!/bin/bash
# ============================================================================
# Source this to make `flutter` mean the SDK pinned in the repo's .fvmrc.
#
# Why: a bare `flutter` is whatever is first on PATH (here the system
# /usr/bin/flutter). When that SDK differs from .fvmrc, its implicit
# `pub get` re-resolves phone_app/pubspec.lock against its own pinned
# test_api and the hook "modifies files" on a fresh checkout. The fix is to
# run the pinned SDK, never to commit a lock for whichever SDK ran last.
#
# With fvm: the pinned SDK's bin goes on PATH (installed on first use),
# placed after any leading */shims entries so build-lock shims still wrap it.
# Without fvm (CI installs the pinned version itself): fail fast on a
# mismatch instead of silently rewriting the lock.
#
# Usage: source "$REPO_DIR/scripts/pinned_flutter.sh" && use_pinned_flutter "$REPO_DIR"
# Requires: jq; fvm when the active flutter is not already the pinned one.
# ============================================================================

# pinned_flutter_version REPO_DIR: print the version pinned in .fvmrc.
pinned_flutter_version() {
    local fvmrc="$1/.fvmrc"
    [[ -f "$fvmrc" ]] || { echo "Error: no $fvmrc" >&2; return 1; }
    jq -er '.flutter' "$fvmrc" || { echo "Error: no .flutter in $fvmrc" >&2; return 1; }
}

# path_with_bin BIN: print PATH with BIN inserted after leading */shims dirs.
path_with_bin() {
    local bin="$1" out="" placed=0 part
    local -a parts
    IFS=':' read -r -a parts <<<"$PATH"
    for part in "${parts[@]}"; do
        if [[ $placed -eq 0 && $part != */shims ]]; then
            out="${out:+$out:}$bin"
            placed=1
        fi
        [[ $part == "$bin" ]] && continue
        out="${out:+$out:}$part"
    done
    [[ $placed -eq 1 ]] || out="${out:+$out:}$bin"
    printf '%s\n' "$out"
}

# use_pinned_flutter REPO_DIR: export PATH so `flutter` is the pinned SDK.
use_pinned_flutter() {
    local version cache bin
    version="$(pinned_flutter_version "$1")" || return 1
    if command -v fvm >/dev/null; then
        cache="$(fvm api context | jq -er '.context.config.cachePath')" || {
            echo "Error: fvm reported no cache path" >&2
            return 1
        }
        bin="$cache/versions/$version/bin"
        if [[ ! -x "$bin/flutter" ]]; then
            fvm install "$version" >&2 || return 1
        fi
        PATH="$(path_with_bin "$bin")"
        export PATH
        return 0
    fi
    local active
    active="$(flutter --version --machine 2>/dev/null | jq -r '.frameworkVersion')"
    if [[ "$active" != "$version" ]]; then
        echo "Error: flutter $active is active but .fvmrc pins $version (install fvm)" >&2
        return 1
    fi
}
