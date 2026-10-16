import 'package:flutter/services.dart';

/// Dart side of the single MethodChannel the Kotlin ring path exposes.
///
/// One channel for the whole feature (see `AlarmChannel.kt`): the alarm must
/// never depend on a pub plugin compiling against AGP 9.
class AlarmScheduler {
  /// Creates a scheduler; [channel] is injectable so tests need no platform.
  AlarmScheduler({MethodChannel? channel})
    : _channel = channel ?? const MethodChannel(channelName);

  /// Channel name, matching `AlarmActivity.CHANNEL` on the Kotlin side.
  static const String channelName = 'com.kuhy.wake_alarm_sync/alarm';

  final MethodChannel _channel;

  /// Which scheduler instance currently owns the NFC handler.
  ///
  /// The handler is per *channel name*, i.e. global, but screens register
  /// and clear it through their own instances. Route replacement runs the
  /// new screen's `initState` before the old screen's `dispose`, so without
  /// ownership the ring screen's dispose wiped the session screen's freshly
  /// registered listener and no session tag was ever heard (2026-09-16, on
  /// the Pixel).
  static AlarmScheduler? _nfcOwner;

  /// Arms the alarm for the next occurrence of [hour]:[minute] in local time.
  ///
  /// The phone rings **daily**, matching the PC's `ALARM_DAYS` (all seven
  /// days) and its baked-in fallback hour. Callers pass a time resolved by
  /// `AlarmPolicy`, never a user-chosen one: the schedule is the daily ramp
  /// and only ever ratchets earlier.
  Future<void> schedule(int hour, int minute) => _channel.invokeMethod<void>(
    'schedule',
    <String, int>{'hour': hour, 'minute': minute},
  );

  // There is deliberately NO cancel(). The alarm cannot be switched off from
  // the app: the only way past it is the full dismiss ritual at ring time.
  // The Kotlin `cancel` handler is gone too, so this is not merely a missing
  // Dart wrapper around a live capability.

  /// Arms the fixed schedule and starts the daily watchdog.
  ///
  /// Called from the app's init seam, so simply launching the app arms the
  /// alarm — there is no button to forget to press.
  Future<void> armSchedule(int hour, int minute) => _channel.invokeMethod<void>(
    'armSchedule',
    <String, int>{'hour': hour, 'minute': minute},
  );

  /// Re-arms from the stored time; false when no alarm was ever set.
  ///
  /// Called from the app's init seam because the store has no change stream:
  /// without this, an app restart that does not touch the picker would leave
  /// nothing armed.
  Future<bool> rearm() async =>
      await _channel.invokeMethod<bool>('rearm') ?? false;

  /// Stops the ring and immediately re-arms for tomorrow.
  Future<void> dismiss() => _channel.invokeMethod<void>('dismiss');

  /// Tells the native side today's ring was actually dismissed.
  ///
  /// Called once, from `SessionHandoff.afterDismiss` regardless of outcome —
  /// reaching that call at all means the dismiss gate was satisfied. Native
  /// pairs this with the fired timestamp it records independently
  /// (`RingWatch`), so an abandoned ring (phone powered off before this
  /// ever runs) can be told apart from a completed one with no Dart engine
  /// required on the next boot.
  Future<void> markRingDismissed() =>
      _channel.invokeMethod<void>('markRingDismissed');

  /// Whether the system will honour the full-screen intent.
  ///
  /// False from API 34 unless granted. The caller must treat this as a hard
  /// failure: without it the alarm posts a notification the sleeper never sees.
  Future<bool> canUseFullScreenIntent() async =>
      await _channel.invokeMethod<bool>('canUseFullScreenIntent') ?? false;

  /// Whether the device can read NFC and has it switched on.
  Future<bool> hasNfc() async =>
      await _channel.invokeMethod<bool>('hasNfc') ?? false;

  /// Calls [onTag] with each NFC tag id scanned while the ring screen is up.
  ///
  /// Reader mode is driven from Kotlin, so the tap does not restart the
  /// activity — a restart would reset the challenge.
  void onNfcTag(void Function(String tagId) onTag) {
    _nfcOwner = this;
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'onNfcTag') {
        final id = call.arguments;
        if (id is String) onTag(id);
      }
      return null;
    });
  }

  /// Starts reader mode so the next tag tapped can be registered.
  ///
  /// Returns false when the device has no NFC or it is switched off, so the
  /// UI can say so rather than waiting on a tap that cannot come.
  Future<bool> startTagRegistration() async =>
      await _channel.invokeMethod<bool>('startTagRegistration') ?? false;

  /// Stops reader mode after registration.
  Future<void> stopTagRegistration() =>
      _channel.invokeMethod<void>('stopTagRegistration');

  /// Stops listening for NFC taps — only if this instance registered them.
  void clearNfcListener() {
    if (_nfcOwner != this) return;
    _nfcOwner = null;
    _channel.setMethodCallHandler(null);
  }

  /// Closes the ring screen after a successful dismiss.
  ///
  /// Without this the dismiss screen stays up over the lockscreen forever —
  /// back is disabled by design — and the live instance would carry a
  /// satisfied room proof and the solved answer into the next ring.
  Future<void> closeRingScreen() =>
      _channel.invokeMethod<void>('closeRingScreen');

  /// Hands the native ring path the current set of free ISO dates.
  ///
  /// The alarm fires from Kotlin with no Flutter engine running, so the
  /// Dart-side pool is invisible at 08:00. This is the cache `AlarmReceiver`
  /// consults before making any noise; it is rewritten after every local
  /// change and every sync, so it is only ever as stale as the last launch.
  Future<void> setFreeDays(List<String> isoDates) => _channel
      .invokeMethod<void>('setFreeDays', <String, Object>{'dates': isoDates});

  /// Hands the native ring path the current set of sick ISO dates: the
  /// same kind of cache as [setFreeDays], kept separately (`SickDays.kt`).
  Future<void> setSickDays(List<String> isoDates) => _channel
      .invokeMethod<void>('setSickDays', <String, Object>{'dates': isoDates});

  /// Reads the native sick-day cache back, sorted: what `AlarmReceiver`
  /// will read at ring time. Null when the native side cannot read it.
  Future<List<String>?> getSickDays() =>
      _channel.invokeListMethod<String>('getSickDays');

  /// Starts the ring immediately, without waiting for the alarm instant.
  ///
  /// Exists so the foreground-service and full-screen-intent path can be
  /// exercised on an emulator; it arms nothing and changes no stored time.
  Future<void> ringNow() => _channel.invokeMethod<void>('ringNow');

  /// Captures the step baseline for this ring.
  Future<void> beginStepCount() =>
      _channel.invokeMethod<void>('beginStepCount');

  /// Steps since [beginStepCount], or -1 when unavailable.
  Future<int> stepsSinceRingStart() async =>
      await _channel.invokeMethod<int>('stepCount') ?? -1;

  /// Arms the morning session's re-ring for the absolute instant [at], or
  /// drops it when [at] is null.
  ///
  /// An AlarmManager alarm, not a Dart timer: the session screen can be
  /// killed, paused or rebooted away mid-session, and the deadline must
  /// survive all three. Replaces any earlier re-ring. Null exists because a
  /// leg can have no deadline (its re-ring is spent, or the morning's are),
  /// and the previous leg's alarm must not fire into it.
  Future<void> armReRing(DateTime? at) => _channel.invokeMethod<void>(
    'armReRing',
    <String, int?>{'atMillis': at?.millisecondsSinceEpoch},
  );

  /// Ends the session: drops the pending re-ring and the session notice.
  ///
  /// The only path that clears a re-ring. Called from the session's own
  /// finish, never from a button — the wake alarm still has no off switch.
  Future<void> finishSession() => _channel.invokeMethod<void>('finishSession');

  /// Hands the native side the live leg: [date] (`yyyy-mm-dd`), its [label]
  /// and the instant it re-rings at, or null when it has no deadline.
  ///
  /// This is what the launcher redirect and the ongoing notification read
  /// (`SessionNotice.kt`), so it must follow every leg change; the
  /// notification counts down by itself, so it need not follow the tick.
  Future<void> updateSessionNotice({
    required String date,
    required String label,
    DateTime? deadline,
  }) => _channel.invokeMethod<void>('updateSessionNotice', <String, Object?>{
    'date': date,
    'label': label,
    'deadlineMillis': deadline?.millisecondsSinceEpoch,
  });

  /// Whether a launch right now is redirected into the morning: a ring is
  /// sounding, or today's session is still on a leg. The probes ask before
  /// starting a test ring on top of it.
  Future<bool> morningLive() async =>
      await _channel.invokeMethod<bool>('morningLive') ?? false;

  /// Whether the ring is sounding right now.
  ///
  /// The session screen polls this every tick. A deadline that fires while
  /// the checklist sits in the background is a heads-up notification plus
  /// sound (an unlocked, in-use phone downgrades the full-screen intent) and
  /// the live `singleInstance` activity is not recreated, so nothing else
  /// would put the dismiss sequence in front of the noise.
  Future<bool> isRinging() async =>
      await _channel.invokeMethod<bool>('isRinging') ?? false;

  /// Raw presence observations: `ssid`, `bssid`, `lat`, `lon`, `accuracy`,
  /// `distanceMeters`, `reason`.
  ///
  /// The home coordinate goes *in* so Kotlin can return `distanceMeters` from
  /// `Location.distanceBetween` — otherwise the policy file would have to
  /// hand-roll Haversine to be unit testable. Null when the platform is
  /// absent, which `HomePresence` reads as unreadable, i.e. away.
  ///
  /// [withFix] makes it wait for a location fix even when Wi-Fi already
  /// answered. Registration wants that; the ring screen does not, because
  /// skipping GPS is what makes the verdict instant at home.
  Future<Map<String, Object?>?> readPresence({
    double? homeLat,
    double? homeLon,
    bool withFix = false,
  }) async {
    final result = await _channel.invokeMapMethod<String, Object?>(
      'readPresence',
      <String, Object?>{
        'homeLat': homeLat,
        'homeLon': homeLon,
        'withFix': withFix,
      },
    );
    return result;
  }
}
