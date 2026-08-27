# Curtains: what to buy, and what the code already does

Item 5 of the hardening plan — "sun curtains open automatically on alarm
trigger". The **software is shipped and wired**; there is no hardware yet. The
alarm already calls `open_curtains()` on its startup path, next to
`turn_on_plug()`, and the default driver logs what it would have done.

So buying a motor is a config file, not a code change:

```bash
cat > ~/.config/wake_alarm/curtains.json <<'JSON'
{"driver": "noop"}
JSON
```

Absent file, malformed file, or an unknown driver name all fall back to the
no-op with a WARNING. A driver that throws is caught and the alarm rings on —
a jammed motor must never be a reason not to be woken.

## Why curtains are worth having at all

The audio failsafe silences the alarm after `FAILSAFE_SILENCE_SECONDS`
(300 s). Daylight is the one wake cue that keeps working after that, and the
only one that does not depend on a speaker, a sink, or a working HDMI
handshake — the exact chain that made this alarm silent in the first place.
It is also the cue that keeps working while you are in the other room solving
the phone's challenge.

## Adding a driver

`_curtains.py` has a two-method `CurtainDriver` protocol (`open`, `close`) and
a `_DRIVERS` registry. A new motor is one class plus one registry entry.

Three rules, all of which the existing no-op and `_smart_plug.py` follow:

1. **Import the dependency inside the factory, guarded.** The service runs
   `/usr/bin/python`, not a venv, so a library that failed to install must
   degrade to the no-op rather than kill the alarm process.
2. **Return, never raise.** `open_curtains()` catches, but a driver that
   blocks forever cannot be caught — give every network call a timeout, the
   way `TAPO_TIMEOUT_SECONDS` does.
3. **Never block the alarm.** The call is on the startup path, ahead of the
   first beep.

## Hardware options

Nothing here is bought or tested — this is a shortlist, not a recommendation
from use. Ordered by how well each fits the constraints above.

### 1. Retrofit chain/rod motor (best fit)

A motor that clamps onto the existing rail, so no new curtains and no
landlord conversation. Look for:

- **Local control** — an HTTP or MQTT endpoint on the LAN. A cloud-only
  device makes a 07:00 wake dependent on someone else's uptime, which is
  precisely the dependency `_sync.py` already works hard to bound.
- **A physical manual override**, so a dead motor is not a dark room.
- **Mains power, not battery.** A battery that dies quietly gives you a
  failure with no symptom until the morning it matters.

Zigbee/Z-Wave models need a hub; a Wi-Fi model with a local API needs none
and is the simpler driver to write.

### 2. Tapo/Kasa-driven mains switch (cheapest path)

If a curtain motor with a hard switch is already in place, a second smart plug
would work through `python-kasa`, which this repo already depends on. Cheapest
by far, but it only works for a motor that opens on power-up — most do not.

### 3. Nothing (the current state)

Genuinely fine. The no-op driver is not a stub awaiting replacement; it is the
correct behaviour for a machine with no motor, and it keeps the log event and
the call site real so nothing has to be rediscovered later.

## What is deliberately not here

- **No cloud integrations.** See the local-control point above.
- **No scheduling of its own.** The alarm decides when morning is; a curtain
  motor with its own timer would be a second source of truth, and the whole
  design of this repo is that the phone is the only one.
- **No "close at night" automation.** `CurtainDriver.close()` exists so a
  driver has both ends implemented, but nothing calls it yet. Closing belongs
  to the night lockdown (item 13), not to the alarm.
