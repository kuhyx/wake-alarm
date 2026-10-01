#!/bin/bash

# ============================================================================
# wake_alarm's default gate for shell and system scripts.
#
# Provisions a disposable Arch guest, installs this repo into it exactly the
# way production does, and runs the cases that cannot safely run on the host:
# install.sh, the systemd units, the shutdown wrapper, the power-key
# inhibitor, and the re-fire path after a cut-short alarm.
#
# What it deliberately cannot cover -- audio, the phone, real outputs, the
# bootloader -- is in DOCS-vmbox.md. Read that before trusting a pass.
#
# Usage: bash scripts/vmbox/harness.sh [--name <sandbox>] [--keep]
# ============================================================================

set -euo pipefail

VM_NAME="wake-alarm-harness"
KEEP=0
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
readonly SCRIPT_DIR
# Absolute and symlink-resolved: `vm share` and `vm repo` both key off the
# path's basename, so a relative "scripts/vmbox/../.." resolves to the wrong
# directory in the guest and rsync writes into /home instead of the repo.
REPO_DIR="$(readlink -f "${SCRIPT_DIR}/../..")"
readonly REPO_DIR
SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME

# The guest image lacks tk, and it is NOT optional even though the alarm's Tk
# window is gone: `_state` imports `gatelock.log_integrity` for the HMAC, and
# `gatelock/__init__.py` imports tkinter at module scope, so `import gatelock`
# dies with "libtk8.6.so: cannot open shared object file" without it. Measured
# in the guest, not guessed -- dropping this package is what broke the harness
# when the alarm window was deleted.
readonly GUEST_PACKAGES="tk alsa-utils"

# Printed by guest_cases.sh only when every case passed. See run_cases().
readonly GUEST_OK_SENTINEL="ALL-CASES-PASSED"

usage() {
    cat <<USAGE
Usage: $SCRIPT_NAME [OPTIONS]

Run wake_alarm's system-level cases in a disposable Arch VM.

Options:
  --name <sandbox>  Sandbox name (default: $VM_NAME)
  --keep            Leave the sandbox running afterwards, for poking at
  -h, --help        Show this help

Exit codes:
  0  every case passed
  1  a case failed
  2  the harness could not run (vmbox missing, provisioning failed)
USAGE
    exit 0
}

die() {
    echo "Error: $*" >&2
    exit 2
}

step() {
    echo "==> $*"
}

validate_requirements() {
    command -v vm >/dev/null 2>&1 ||
        die "vmbox is not installed. Run: bash ~/src/utils/vmbox/install.sh"
    [[ -f "$REPO_DIR/install.sh" ]] ||
        die "cannot find install.sh; run this from the wake-alarm repo"
}

# Bring the sandbox up from scratch. `vm new` on an existing name is an error,
# so an existing sandbox is reset instead -- that is the sub-second path and
# it guarantees a pristine starting point either way.
provision_sandbox() {
    if vm list 2>/dev/null | awk '{print $1}' | grep -qx "$VM_NAME"; then
        step "Resetting existing sandbox '$VM_NAME'"
        vm reset "$VM_NAME" >/dev/null
    else
        step "Creating sandbox '$VM_NAME'"
        vm new "$VM_NAME" >/dev/null
    fi

    # `vm repo` copies out of the shared mount, so the share must exist first.
    # A bind mount, never a symlink: 9p does not follow one.
    step "Sharing the repo with the guest"
    vm share "$REPO_DIR" >/dev/null

    # `vm new`/`vm reset` leave the sandbox STOPPED, and there is no `vm up`;
    # `vm run` is what boots it, and `vm repo` needs it running.
    step "Installing guest packages ($GUEST_PACKAGES)"
    vm run "$VM_NAME" \
        "sudo pacman -S --noconfirm --needed $GUEST_PACKAGES" >/dev/null ||
        die "could not install guest packages"

    # --worktree, not a clone: the point of the gate is to test the edits in
    # front of you, including the ones not committed yet.
    step "Copying the working tree into the guest"
    vm repo "$VM_NAME" "$REPO_DIR" --worktree >/dev/null ||
        die "could not copy the repo into the guest"
}

# The real production install path, not a hand-rolled approximation: this is
# the same install.sh a machine runs, so a break in it fails the gate.
run_install() {
    step "Running install.sh in the guest"
    # `vm run` reports the VM's verdict, not the guest command's exit status,
    # so this must confirm success from the OUTPUT. Trusting the exit code let
    # a guest ImportError through as a pass, and the three cases downstream
    # then failed with no hint that the install was the cause.
    # `vm repo` lands the tree at ~/<basename> in the guest, whatever the
    # host layout is: the 2026-09-11 home-tidy re-pointed this to ~/src and
    # the gate went red for a week without anyone noticing, because the
    # sentinel grep below matched vm's echo of the command line itself.
    # Hence -x: only a line that IS the sentinel counts.
    vm run "$VM_NAME" \
        'cd ~/wake-alarm && bash install.sh && echo INSTALL-OK' \
        >/tmp/wa-install.log 2>&1 || true
    if ! grep -qx 'INSTALL-OK' /tmp/wa-install.log; then
        tail -20 /tmp/wa-install.log >&2
        die "install.sh failed in the guest (full log: /tmp/wa-install.log)"
    fi
}

# `vm run` reports the *VM's* verdict (clean/dirty/hung), not the command's
# exit status -- a guest script exiting 1 still gives rc=0 on the host. That
# would make this gate fail *open*, which is worse than having no gate, so the
# verdict is carried in the output as an explicit sentinel and matched here.
run_cases() {
    step "Running the guest cases"
    local output
    output="$(vm run "$VM_NAME" \
        'bash ~/wake-alarm/scripts/vmbox/guest_cases.sh all' 2>&1)"
    echo "$output"
    grep -q "$GUEST_OK_SENTINEL" <<<"$output"
}

cleanup() {
    if [[ $KEEP -eq 1 ]]; then
        echo "Sandbox '$VM_NAME' left running (--keep). Poke at it with: vm ssh $VM_NAME"
        return
    fi
    vm reset "$VM_NAME" >/dev/null 2>&1 || true
}

main() {
    validate_requirements
    trap cleanup EXIT

    provision_sandbox
    run_install

    local status=0
    run_cases || status=1

    echo "============================================================"
    if [[ $status -eq 0 ]]; then
        echo "vmbox harness: PASSED"
        echo "NOT verified on the host — see DOCS-vmbox.md for what this misses."
    else
        echo "vmbox harness: FAILED"
    fi
    echo "============================================================"
    return $status
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --name)
            VM_NAME="${2:?--name needs a sandbox name}"
            shift 2
            ;;
        --keep)
            KEEP=1
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

main "$@"
