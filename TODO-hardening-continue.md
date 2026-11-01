# Wake-alarm hardening — residue

REMOVE ME AFTER FINISH

Phases 0-7 shipped. The PC alarm window, gate and `_alarm.py` were deleted in
`e67cef0` (2026-08-30), so the old "item 8 mutual gating" (PC half) no longer
has anything to gate and was dropped. Context: `DOCS-wake-enforcement.md`.

## Remaining

1. **Item 13, black screen.** Host-only, other repo
   (`~/src/testsAndMisc/linux_configuration`). The original plan file
   (`~/.claude/plans/wake-alarm-still-does-witty-toucan.md`) is gone, so the
   symptom is no longer written down: needs kuhy to restate it, or drop it.
2. **Two-tag dismiss sequence, end to end on the Pixel.** Needs kuhy: a second
   physical NFC tag (only one is registered, so every on-device run fell
   through to the 5-minute bypass).
3. **Locked-keyguard dismiss, run to completion.** Needs kuhy: a run with a
   locked phone (PIN-prompt path is implemented but unproven).

## done

Items 1-3 each confirmed on the phone or dropped by kuhy; then delete this file.
