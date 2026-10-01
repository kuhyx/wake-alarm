import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/enforcement_state.dart';

/// Dart side of the wake-enforcement methods (`EnforcementChannel.kt`).
///
/// The same single alarm channel as [AlarmScheduler] -- a separate class
/// only so that file stays under the line cap and this one stays about one
/// thing: reading the native stick and the event log, and the escape.
class EnforcementBridge {
  /// Creates a bridge; [channel] is injectable so tests need no platform.
  EnforcementBridge({MethodChannel? channel})
    : _channel = channel ?? const MethodChannel(AlarmScheduler.channelName);

  final MethodChannel _channel;

  /// Appends a Dart-side event to the native log, stamped natively.
  Future<void> appendEvent(
    String kind, [
    Map<String, Object?> data = const <String, Object?>{},
  ]) => _channel.invokeMethod<void>('appendEvent', <String, Object?>{
    'kind': kind,
    'data': data,
  });

  /// The whole event log, newest first; empty when the platform has none.
  Future<List<Map<String, Object?>>> readEvents() async {
    final text = await _channel.invokeMethod<String>('readEvents');
    if (text == null) return const <Map<String, Object?>>[];
    final decoded = jsonDecode(text);
    if (decoded is! List) return const <Map<String, Object?>>[];
    return <Map<String, Object?>>[
      for (final entry in decoded)
        if (entry is Map) Map<String, Object?>.from(entry),
    ];
  }

  /// The native stick; null when the platform answers nothing usable.
  Future<EnforcementState?> state() async => EnforcementState.fromMap(
    await _channel.invokeMapMethod<Object?, Object?>('enforcementState'),
  );

  /// Marks today escaped natively, clears the streak and lifts the
  /// lockdown; false when the hatch has closed.
  Future<bool> escapeToday() async =>
      await _channel.invokeMethod<bool>('escapeToday') ?? false;
}
