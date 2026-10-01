import 'dart:developer' as developer;
import 'dart:ui' show DartPluginRegistrant;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:wake_alarm_sync/services/ring_start_recorder.dart';

/// Channel `HeadlessRingStart.kt` listens on for `done`.
const headlessChannelName = 'com.kuhy.wake_alarm_sync/headless';

/// The headless engine's whole job: publish `ring_started`, then say done.
///
/// Started natively when the daily alarm fires (`ringStartedMain` in
/// `main.dart`), so the PC learns the phone is ringing even when the ring
/// screen never opens. `done` is sent whatever happened -- the native side
/// would otherwise keep a second engine alive until its timeout.
Future<void> runHeadlessRingStart({
  RingStartRecorder? recorder,
  MethodChannel? channel,
}) async {
  WidgetsFlutterBinding.ensureInitialized();
  // A non-`main` entrypoint does not register Dart-side plugin
  // implementations (shared_preferences, secure storage) by itself.
  DartPluginRegistrant.ensureInitialized();
  try {
    await (recorder ?? RingStartRecorder(openedEvent: null, source: 'alarm'))
        .record();
  } finally {
    try {
      await (channel ?? const MethodChannel(headlessChannelName))
          .invokeMethod<void>('done');
    } on Object catch (e) {
      developer.log('headless done not delivered: $e', name: 'WakeAlarmRing');
    }
  }
}
