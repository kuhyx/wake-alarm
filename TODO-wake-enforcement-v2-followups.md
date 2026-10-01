# Wake enforcement v2 — follow-ups for the next session

REMOVE ME AFTER FINISH

Handoff from the 2026-10-01 session that built v2. Read
`DOCS-wake-enforcement.md` (the contract + verification status) and
`AGENTS.md` first. Start **after the morning of 2026-10-02** so there is real
evidence to check.

## Prompt to paste into the new session

> Work through ~/src/wake-alarm/TODO-wake-enforcement-v2-followups.md top to
> bottom. Verify each item yourself on the real target (phone 23181JEGR08034,
> this PC) before calling it done, then delete the TODO file in the final
> commit.

## 1. Check the first real morning (2026-10-02, Fri, carrot day)

- `python -m wake_alarm._audit 2026-10-02` (and the 11:05 file in
  `~/data/wake-alarm/incidents/`). Expected: phone `alarm_fired`
  (`reason=daily`), `ring_started_published` with `source=alarm` (headless
  engine, release build — never verified in release before) or
  `ring_screen`, `stick_check` verdict for a non-stick day, no fallback ring
  unless the phone really was silent.
- `adb logcat` for `WakeAlarmHeadless` / `WakeAlarmStick*` if anything is
  missing. Firebase fields `ring_started`, `phone_events` must be non-empty
  (`enforcement_view(fetch_firebase_logs())`).
- Any MISMATCH in the report is a bug to fix, not a note.

## 2. focus-owner reacting to a real lockdown (needs kuhy's OK + timing)

Never verified on the Pixel. Either wait for the first real Tue/Wed/Thu miss
and read focus-owner's Debug log (`LOCKDOWN_ACTIVATED` with the through-date,
then a `WORKDAY_LOCKDOWN` pass), or — with kuhy's explicit OK, at a time he
names — trigger one and lift it with the escape button (logs an escape).

## 3. Root ring vs a card held busy by PipeWire

Host test 2026-10-01: `wake-alarm-ring-alsa.service` got `Device or resource
busy` while the user's PipeWire held card `Generic_1` (ALC897). kuhy approved
killing the holder (`fuser -k -TERM /dev/snd/pcmC<N>D0p` after 3 busy opens,
in `scripts/pc/ring_alsa.sh`), but the auto-mode classifier refused the edit
twice. **kuhy must add a permission rule first**, or choose the non-killing
alternative: when the root unit cannot open the card, `_ring_player` falls
back to `PipeWireBackend` (PipeWire holds the card, so it can mix the ring
in). Add a vmbox case that holds `snd-dummy` open and proves the ring still
plays.

## 4. S5 (poweroff) RTC wake test on the host

Hibernate (S4) wake is verified and is the default mode. S5 is not. The
self-resume boot unit (`~/data/claude-scratch/wake-fw/s5_after_boot.sh`,
never installed) was refused by the classifier. Simplest: with kuhy present,
`sudo -n rtcwake -m no -s 240` + record the epoch, `systemctl poweroff`; kuhy
powers on if it does not wake; then compare `uptime -s` with the epoch. If S5
works, decide with kuhy whether to switch `pc_wake.json` to `poweroff` (covers
a typed `shutdown`, not just the power key).

## 5. utils dependency upgrade — prepared, uncommitted

In `~/src/utils` (do NOT stage the other session's `ts_config/README.md`,
`scripts/lib/alias-imports.mjs`, `test/alias-imports.test.js`): pylint 4.1.1
×3, typescript-eslint 8.71.0 (ts_config/ts_core/web_ui), @eslint-react
5.23.3, eslint-plugin-sonarjs 4.2.2, pnpm 12.8.1 (+ lockfiles,
`ts_config/pnpm-workspace.yaml`), allowlist: typescript-eslint entry removed,
typescript entry now `blocked_by: transitive:typescript-eslint@8.71.0`.
Lint + tests pass in all three. `finish_auto.sh` fails at its test step with
corepack `MODULE_NOT_FOUND .../pnpm/12.8.1/bin/pnpm.cjs` (pnpm 12.8 ships a
native binary; corepack 0.36 can't launch it). Global pnpm 12.8.1 is now
installed directly (`corepack disable pnpm`); find what in the gate still
calls corepack (read `~/data/claude-scratch/wake-v2/utils-commit.log`), fix,
commit, watch CI green.

## 6. Fleet repos still pinning typescript-eslint 8.70.0

The allowlist entry that excused them is gone, so their freshness gate turns
red on the next run: konbini-67, iron-and-anvil, awesome-mcp-explorer,
europe-county-map and any other repo pinning it (`grep -rl
'"typescript-eslint": "8.70.0"' ~/src --include=package.json`). Bump each to
8.71.0, lint + test, commit, CI green.

## 7. Small leftovers

- `~/src/todo`: `cupertino_icons` 1.0.9 → 2.0.0 — another session had
  uncommitted work there; only bump once its tree is clean.
- Global `~/.claude/CLAUDE.md` sandbox-first note says the vmbox guest is
  BIOS-only; vmbox has `--uefi` and `vm wake` (RTC-wake emulation) since
  utils 694c013. Ask kuhy before editing that file.
- Clear the test data left in the `wake_alarm_api36` emulator (escape for
  10-01, ringStarted, stick state) before it is ever signed into sync.
