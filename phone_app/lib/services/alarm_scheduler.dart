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

  /// Arms the alarm for the next occurrence of [hour]:[minute] in local time.
  ///
  /// The phone rings **daily**, matching the PC's `ALARM_DAYS` which is
  /// currently all seven days. The two are deliberately not synced — a shared
  /// day set is item 8's shape, and diverging defaults would have the halves
  /// firing on different days.
  Future<void> schedule(int hour, int minute) =>
      _channel.invokeMethod<void>('schedule', <String, int>{
        'hour': hour,
        'minute': minute,
      });

  /// Cancels the armed alarm and forgets the stored time.
  Future<void> cancel() => _channel.invokeMethod<void>('cancel');

  /// Re-arms from the stored time; false when no alarm was ever set.
  ///
  /// Called from the app's init seam because the store has no change stream:
  /// without this, an app restart that does not touch the picker would leave
  /// nothing armed.
  Future<bool> rearm() async =>
      await _channel.invokeMethod<bool>('rearm') ?? false;

  /// Stops the ring and immediately re-arms for tomorrow.
  Future<void> dismiss() => _channel.invokeMethod<void>('dismiss');

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

  /// Stops listening for NFC taps.
  void clearNfcListener() => _channel.setMethodCallHandler(null);

  /// Closes the ring screen after a successful dismiss.
  ///
  /// Without this the dismiss screen stays up over the lockscreen forever —
  /// back is disabled by design — and the live instance would carry a
  /// satisfied room proof and the solved answer into the next ring.
  Future<void> closeRingScreen() =>
      _channel.invokeMethod<void>('closeRingScreen');

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
}
