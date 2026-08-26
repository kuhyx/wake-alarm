# Speaker recommendation — bedroom wake alarm

Item 7 of the alarm-hardening work. **Prose only; no code changes here.**

## Why the software cannot solve this

A powered-off speaker is **undetectable from software**. Measured on this
machine: the analog sink is present and `IDLE` whether or not the amplifier has
mains power.

```
$ pactl list short sinks
61  alsa_output.pci-0000_0d_00.6.analog-stereo  PipeWire  s32le 2ch 48000Hz  IDLE
```

Nothing in `_list_real_sinks()` can distinguish "playing to speakers" from
"playing to an amp that is switched off". Designing detection here would be
shipping a placebo. The fix is hardware plus the smart plug that is *already*
integrated.

## The deciding spec is the power switch, not the LED

`_alarm.py` already calls `turn_on_plug()` when the alarm fires and
`turn_off_plug()` from `on_close()` — which runs on every exit path including
SIGTERM. So the "cut mains overnight, restore at alarm time" architecture is
already implemented; it simply has no plug configured yet
(`~/.config/wake_alarm/tapo.json` does not exist).

That makes one criterion pass/fail, ahead of everything else:

> **GATE — the speaker must come back ready to pass audio when mains returns,**
> with no button press and no standby state.

A **latching mechanical** switch (rear rocker, or a volume pot with a click-off
detent) holds its position through a mains cut, so the unit re-energises in the
state it was left in. A **momentary / soft-touch / microcontroller** button has
no mechanical memory and boots into whatever firmware defaults to — usually
standby. That is disqualifying.

**Rule of thumb: a remote control in the box = disqualified.** Anything with a
remote has a standby microcontroller.

## Verified findings (official manuals / vendor FAQs only)

| Model | Switch | LED | Verdict |
|---|---|---|---|
| **Edifier R1280T** ~299–309 zł | Rear latching rocker, **no remote** | Blue, front | ✅ **Top pick** |
| Edifier R1280DB / R1700BT / R1855DB | Has remote → soft standby | — | ❌ see below |
| **Mackie CR3-X** ~ | Rear rocker **+** front click-off pot, no standby | White logo ring, **cannot be defeated** | ⚠️ gate-passes, light fails |
| **M-Audio BX3** | Front click-detent pot (no rear switch) | Front LED | ✅ runner-up |
| **JBL 104** | Rear latching | Front ring around volume knob | ⚠️ auto-standby after 19 min |
| PreSonus Eris E3.5 (non-BT) | Front latching On/Off | Solid blue | ⚠️ ok, but see BT note |
| PreSonus Eris **BT** models | — | Red in standby | ❌ 15-min standby, **up to 30 s wake delay** |
| **SVEN SPS-702** ~239 zł | Rear mains rocker, no remote, analogue pots | Single pinhole | ✅ budget pick |
| Creative Pebble Pro | RGB button cycles to Off | persistence unverified | ⚠️ unverified |

### The Edifier trap, worth stating explicitly

Edifier's own support article (R1280DB/DBS standby): powering down with the
remote activates **standby** — the LED goes off but the physical switch stays
on, and *"the only way to wake the speakers is to use the same remote power
button."* A mains cycle will **not** clear that state. So any Edifier with a
remote breaks the smart-plug architecture. The plain **R1280T has no remote**,
which is exactly why it is the right pick.

### Disqualified on wake latency

PreSonus Eris BT: standby after 15 minutes, and waking costs *"delay up to half
a minute until audio playback is heard."* An alarm that starts half a minute
late is a broken alarm. JBL 104 has the same class of problem (19-minute
standby), though it can be disabled via a headphone-jack toggle sequence.

## Recommendation

1. **Edifier R1280T (~299–309 zł)** — passes the gate (rear latching rocker, no
   remote, no standby state to get stuck in), loud enough at 42 W RMS, analogue
   volume pot so the level survives a power cycle. Its blue front LED is the
   one drawback → cover it with a LED-blackout sticker ("LEDim", biohac.pl, or
   any Allegro *naklejki blokujące światło LED*). Cheap, reversible, no warranty
   impact.
2. **SVEN SPS-702 (~239 zł)** — budget alternative, same topology (rear mains
   rocker, no remote, analogue pots), 40 W RMS, single pinhole LED.

**Avoid** anything with a remote, and avoid Mackie CR3-X for a *bedroom* (its
white logo ring cannot be turned off while powered — vendor FAQ confirms).

## Analog, not USB

Keep the speakers on **analog 3.5 mm**, not USB. A USB speaker disappears from
PipeWire when its mains is cut and re-enumerates on restore, reintroducing
exactly the `auto_null`-only sink race that caused the 2026-07-11 silent alarm.
An analog sink stays present regardless of the speaker's power state.

## Required code change (tracked separately)

`_alarm.py`'s `main()` runs `turn_on_plug()` immediately before
`WakeAlarm(...).run()` — **zero lead time**. An amplifier's soft-start / mute
relay typically delays output 1–5 s after mains is applied, which would swallow
the opening of the alarm. Add a configurable pre-roll delay between plug-on and
the first beep.
