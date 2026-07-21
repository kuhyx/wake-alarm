# Design audit — wake-alarm

Generated against safe-design-rules (anthonyhobday.com/sideprojects/saferules).
Report only — nothing in this repo was changed by the audit itself.

This repo has two distinct UI surfaces, audited separately below:
1. Flutter app — `phone_app/lib/` (theme in `main.dart`, screens in `screens/`)
2. Python/Tkinter alarm dismiss-challenge UI — `wake_alarm/_alarm.py`

Passing/violation/N-A counts per surface are given at the top of each section
so all 28 rules are accounted for even though only violations get expanded.

---

## Flutter app (`phone_app/`)

Theme entry point: `phone_app/lib/main.dart:17-21` —
`ThemeData.dark(useMaterial3: true).copyWith(colorScheme:
ColorScheme.fromSeed(seedColor: Colors.orange, brightness: Brightness.dark))`.
Material 3's `fromSeed` auto-generates near-black surfaces, tinted neutrals,
and contrast-checked roles, so rules 1/2/3/9/10/18 pass "for free" via the
theme — the actual findings are places where code reaches for a literal
`Colors.*` constant instead of a role from that scheme, or a shadow/padding
value the theme doesn't control.

Verdict roster: Pass — 1,2,3,8,10,17,18,23,26. Violation — 4,9(partial,
see notes),11,20,26(Card),28. N/A — 5,6,7,12,13,14,15,16,19,21,22,24,25,27.
(9 and 26 appear in both lists — see the per-rule notes.)

### Violations

- **Rule 4 (everything deliberate)** — `phone_app/lib/screens/home_screen.dart:198-199` and
  `settings_screen.dart:126-128,161,245` use raw `Colors.redAccent` /
  `Colors.greenAccent` / `Colors.red` for status/error text instead of
  `Theme.of(context).colorScheme.error` (or a `tertiary`/success role);
  `home_screen.dart:207` uses raw `Colors.orange` and `settings_screen.dart:138`
  uses raw `Colors.grey` for the same reason. None of these are derived from
  the seeded `ColorScheme`, so they won't stay in sync if the seed color ever
  changes, and they bypass whatever contrast guarantee `fromSeed` gives the
  rest of the app. → Replace with `colorScheme.error` / a defined success
  color / `colorScheme.onSurfaceVariant`.
- **Rule 9 (distinct brightness / no competing colors)** — `home_screen.dart:198-199`
  vs `settings_screen.dart:126-128,161`: `Colors.redAccent`/`Colors.greenAccent`
  are reused ad hoc as the only "status" signal color pair across two separate
  screens with no shared definition — not a brightness clash per se, but an
  undeliberate ad-hoc pairing (same root cause as rule 4).
- **Rule 11 (mathematically related measurements)** — the app mostly uses an
  8px scale (`home_screen.dart:149,154,165,170,191,203` = 32/16/8/32/24/16;
  `settings_screen.dart:93,98,121,131` = 16/16/16/32) but breaks it twice:
  `settings_screen.dart:111` (`padding: EdgeInsets.symmetric(vertical: 14)`)
  and `settings_screen.dart:163` (`SizedBox(width: 12)`) — 14 and 12 aren't on
  the 8px grid the rest of the file uses. → change to 16/8 or otherwise round
  to the established scale.
- **Rule 20 (body text ≥16px)** — `settings_screen.dart:138`:
  `TextStyle(fontSize: 12, color: Colors.grey)` for the PC-config help text is
  below the 16px minimum. `home_screen.dart:153` (`fontSize: 16`) and other
  `fontSize: 18` usages are fine.
- **Rule 26 (no shadows in dark interfaces)** — `settings_screen.dart:154`
  (`return Card(...)`) is an unmodified Material 3 `Card`, which renders with
  default elevation (a soft shadow/tonal overlay) inside a `ThemeData.dark()`
  app (`main.dart:17`). Per the rule, dark UIs should avoid shadows entirely.
  → Either set `elevation: 0` and rely on a filled/tonal surface color for
  the card, or accept the default and drop this from future review — flagging
  now since it's the only place shadows appear at all (see rule 27 below).
- **Rule 28 (lower icon contrast next to text)** — `settings_screen.dart:159-162`
  (`Icon(connected ? Icons.check_circle : Icons.cancel, color: connected ?
  Colors.greenAccent : Colors.redAccent)`) sits directly next to `Text(...)`
  at full theme-text contrast — the icon isn't dimmed relative to the
  adjacent label. Same issue for the settings-gear `IconButton` at
  `home_screen.dart:133-134` (default `Icons.settings` color, undimmed, next
  to the "Wake Alarm Sync" AppBar title).

### Not applicable

- Rule 5 (optical alignment) — only stock Material icons/text used, no custom
  shapes needing eyeballed alignment.
- Rule 6 (letter-spacing/line-height by size) — no explicit `letterSpacing`/
  `height` overrides anywhere in `phone_app/lib/` (grep confirmed); relies on
  Material defaults, nothing to audit.
- Rule 7 (border contrast) — no `Border`/`BorderRadius`/`border:` usage found
  anywhere under `phone_app/lib/` (grep confirmed); no borders exist.
- Rule 12 (order by visual weight) — single linear `Column` per screen, no
  competing-weight layout to order.
- Rule 13 (12-column grid) — single-column mobile screens, no grid layout.
- Rule 14 (space between high-contrast points) — can't be assessed from
  source; spacing is via `SizedBox`/`Padding` bounding boxes, not measured
  edge-to-edge.
- Rule 15 (closer = lighter) — the one elevated element (`Card`,
  `settings_screen.dart:154`) follows M3's automatic surface-tint elevation
  overlay, which already lightens on elevation — no manual z-stack to check.
- Rule 16 (shadow blur = 2x distance) — shadow is Material's default (see
  rule 26), not a custom `BoxShadow`, so there's no explicit offset/blur pair
  to check a ratio on.
- Rule 19 (outer padding ≥ inner) — `settings_screen.dart:93` outer body
  padding (16) vs `settings_screen.dart:156` `_StatusCard`'s own inner
  padding (16): equal, satisfies "≥". `home_screen.dart:149` outer padding
  (32) vs the button's inner vertical padding (16, `home_screen.dart:186`):
  outer > inner. Both pass, no violation to report.
- Rule 21 (line length ~70 chars) — only short status strings/labels; the one
  paragraph (`settings_screen.dart:132-137`) is already manually broken into
  short lines, no long unbroken runs to measure.
- Rule 22 (button padding horizontal = 2x vertical) — `home_screen.dart:185-188`
  and `settings_screen.dart:110-113` only override `vertical` padding
  (16 and 14) and leave horizontal at the `ElevatedButton` theme default —
  the actual rendered ratio can't be read from source alone.
- Rule 24 (nest corners) — no custom `BorderRadius` anywhere (grep
  confirmed), only default Material shapes.
- Rule 25 (adjacent hard divides) — only one `Divider` in the whole app
  (`settings_screen.dart:131`), not adjacent to another border/transition.
- Rule 27 (don't mix depth techniques) — only one depth technique appears at
  all (the `Card`'s default elevation, rule 26) — nothing to mix.

### Notes

- No dedicated `theme.dart` — the `ColorScheme`/`ThemeData` is inline in
  `main.dart:17-21`. That's fine at this size (2 screens), but every raw
  `Colors.*` literal found above is a spot that would have been caught by a
  lint/review pass if a shared palette module existed to import from instead.

---

## Python/Tkinter alarm UI (`wake_alarm/_alarm.py`)

No shared style/constants module exists for color or font — confirmed via
`find` (no `theme`/`style`/`colors` module under `wake_alarm/`) and via
`_constants.py`, which defines timing/day constants but nothing visual.
Every `tk.Label`/`tk.Frame`/`tk.Entry` call in `_alarm.py` repeats its own
hex-color and `font=(...)` tuple literal inline (confirmed: `_alarm.py:166,
172-174,181-183,190-192,200-206,209-211,219-224,228-232,326-331,409`). This
structural absence is itself the rule 4 finding — it also means the same
rule (e.g. rule 2, rule 10) is violated independently at every call site
rather than in one place, so a future fix should introduce a small
`_style.py`/constants block rather than patch each `tk.Label(...)` call.

Verdict roster: Pass — 3,8,17,20,21,23,26,27. Violation — 1(partial),
2,4,9(mixed reuse—see below),10,11,12. N/A — 5,6,7,13,14,15,16,18,19,22,24,25,28.

### Violations

- **Rule 1 (near-black/near-white, not pure)** — `_alarm.py:166` (`bg="#1a1a1a"`)
  correctly uses near-black, not pure black — that part passes. But
  `_alarm.py:191-192` (`info_label`, `fg="white"`) uses **pure white** text,
  which the rule explicitly calls out to avoid. → use an off-white like
  `#e8e8e8`/`#f0f0ee` instead of the literal `"white"`.
- **Rule 2 (saturate your neutrals)** — the only "neutral" grey values used
  are perfectly desaturated (zero-chroma) greys: `_alarm.py:232`
  (`timer_label`, `fg="#aaaaaa"`) and `_alarm.py:305` (hidden-code flash
  state, `fg="#555555"`). Neither has any color tint, so they read as
  generic gray rather than part of the warm/cool palette the rest of the
  screen uses (see rule 10). → tint both toward the same hue family as the
  accent colors (e.g. a warm dark gray like `#4a3f3f` / `#8a7d7d`).
- **Rule 4 (everything deliberate / centralize styling)** — see the surface
  intro above; every color/font is a repeated inline literal across
  `_alarm.py:166-234` and `_alarm.py:326-331`, with no single source of
  truth. → extract a small `_COLORS`/`_FONTS` mapping (mirroring the
  existing `_constants.py` pattern for non-visual constants) and reference
  it from every widget call.
- **Rule 9 (distinct brightness / deliberate reuse)** — `title_label`
  (`_alarm.py:173`, `fg="#ff4444"`) and `status_label`
  (`_alarm.py:223`, `fg="#ff4444"`) reuse the exact same color for two
  different semantic roles ("WAKE UP!" heading vs. a transient error/status
  message) with no evidence it was a deliberate choice rather than
  copy-paste — flagging alongside rule 4 since fixing the missing style
  module would force this decision to be made explicitly.
- **Rule 10 (warm OR cool, not both)** — the screen simultaneously uses warm
  reds/ambers (`_alarm.py:173` `#ff4444`, `:182` `#ffaa00`, `:409`
  `#ff0000` flash) and a fully saturated cool green (`_alarm.py:204,263,274,
  347` `#00ff00`) on the same screen at the same time. → pick one
  temperature family for the "safe/positive" accent (e.g. a warm amber-green
  or switch the alert red to a cooler red) so the palette reads as one
  coherent set rather than a stoplight.
- **Rule 11 (mathematically related measurements)** — `pady` values across
  the widget stack are `20, 5, 10, 30, 10, 10, 5` (`_alarm.py:176, 185, 194,
  207, 215, 226, 235`) — mostly multiples of 5/10, but `pady=5` at lines 185
  and 235 breaks the 10/20/30 pattern used by the surrounding widgets.
  → round the two `pady=5` calls to `10` for a consistent scale.
- **Rule 12 (order by visual weight)** — the largest, boldest element on
  screen is `code_label` at up to 72pt bold (`_alarm.py:198-206`,
  `code_font_size = 48 if ... else 72`), sitting in the visual middle of the
  stack, while the actual title (`_alarm.py:172`, 48pt bold) anchors the top
  edge and the lightest elements (`timer_label`, 14pt, `_alarm.py:231`) sit
  at the bottom edge. The rule wants the heaviest element toward an outer
  edge, not buried in the middle. → this is likely intentional here (the
  code you must type back is the whole point of the screen), so treat as a
  judgment-call violation to confirm rather than an unambiguous bug.

### Not applicable

- Rule 5 (optical alignment) — only text `Label`s stacked via `.pack()`, no
  asymmetric shapes/icons to align by eye.
- Rule 6 (letter-spacing/line-height by size) — Tkinter's `font=(family,
  size, weight)` tuple has no letter-spacing/line-height control at all;
  not expressible in this toolkit.
- Rule 7 (border contrast) — no `relief`/`highlightthickness`/`borderwidth`
  set on any widget (grep confirmed); nothing has a visible border.
- Rule 13 (12-column grid) — single fullscreen widget centered via
  `.place(relx=0.5, rely=0.5)` (`_alarm.py:167`), no grid layout in use.
- Rule 14 (space between high-contrast points) — `pack(pady=...)` controls
  bounding-box spacing, not measured edge-to-edge visual contrast; not
  determinable from source.
- Rule 15 (closer = lighter) — Tkinter has no z-stack/elevation concept;
  this is a flat 2D layout on one background plane.
- Rule 16 (shadow blur = 2x distance) — no shadow effects implemented
  anywhere in the file.
- Rule 18 (container brightness limits) — only one background plane exists
  (`#1a1a1a`, toggled with a full-screen alert flash to `#ff0000` at
  `_alarm.py:409` — not a stacked container), so there's no second surface
  brightness to compare it against.
- Rule 19 (outer padding ≥ inner) — `container` (`_alarm.py:166`) has no
  configured padding of its own; only individual children set `pady`. No
  outer/inner pair exists to compare.
- Rule 22 (button padding) — no `tk.Button` widget exists anywhere in the
  file (grep confirmed) — dismissal is via `tk.Entry` + `<Return>` bind
  (`_alarm.py:209-217`), not a button.
- Rule 24 (nest corners) — Tkinter widgets are square by default with no
  corner-radius concept; not implemented here.
- Rule 25 (adjacent hard divides) — no border/divider lines used anywhere.
- Rule 28 (icon contrast next to text) — no icons used anywhere in this UI;
  text-only.

### Passes (brief)

- Rule 3 (high contrast for important elements) — `_alarm.py:172-174`
  "WAKE UP!" title in `#ff4444` on `#1a1a1a` background is clearly the
  highest-contrast element on screen.
- Rule 8 (align with something) — `container.place(relx=0.5, rely=0.5,
  anchor="center")` (`_alarm.py:167`) plus uniform `.pack()` centering means
  every widget shares the same center-alignment axis.
- Rule 17 (simple on complex) — flat solid `#1a1a1a` background behind flat
  text (`_alarm.py:166`) is plain-on-plain throughout; no visual noise.
- Rule 20 (body text ≥16px) — smallest font used is 14pt
  (`_alarm.py:231`, `timer_label`) ≈ 18-19px at typical DPI, above the 16px
  floor; all other labels are 18pt+ (`_alarm.py:190,222`) or larger.
- Rule 21 (line length ~70 chars) — only short single-line status strings
  are used (longest is ~55 characters, `_alarm.py:372`); no wrapped
  paragraph text to overflow the readable range.
- Rule 23 (two typefaces max) — exactly two families used throughout,
  `"Arial"` and `"Courier"` (`_alarm.py:172,181,190,203,211,222,231,329`) —
  at the limit, not over it.
- Rule 26 (no shadows in dark interfaces) — trivially satisfied: no shadow
  effects are implemented anywhere in this file.
- Rule 27 (don't mix depth techniques) — trivially satisfied: zero depth
  techniques are used, so none can conflict.

### Notes

- The most impactful single fix for this surface is structural, not any one
  color/font value: introduce one `_style.py` (or a `_COLORS`/`_FONTS` dict
  in `_constants.py`) and reference it from every `tk.Label`/`tk.Frame` call
  in `_alarm.py`. That alone would make rules 2, 9, 10, and 11 fixable in one
  place instead of ~15 separate call sites.
