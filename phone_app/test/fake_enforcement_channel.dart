import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/iso_time.dart';

/// Stands in for `EnforcementChannel.kt` on the alarm channel: an event log
/// in memory, a canned stick state and a canned escape answer. Every other
/// method answers null, like the ring tests' own mocks.
class FakeEnforcementChannel {
  /// Every call received, in order.
  final List<MethodCall> calls = <MethodCall>[];

  /// The native event log, newest first.
  final List<Map<String, Object?>> events = <Map<String, Object?>>[];

  /// What `enforcementState` returns.
  Map<String, Object?>? state;

  /// What `escapeToday` returns.
  bool escapeResult = true;

  /// The clock stamping appended events.
  DateTime Function() now = DateTime.now;

  /// The method names received, in order.
  List<String> get methods => calls.map((c) => c.method).toList();

  /// The alarm channel this fake answers on.
  MethodChannel get channel => const MethodChannel(AlarmScheduler.channelName);

  /// Installs the fake for the current test and removes it afterwards.
  void install() {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          ..setMockMethodCallHandler(channel, _handle);
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
  }

  Future<Object?> _handle(MethodCall call) async {
    calls.add(call);
    final args = call.arguments;
    switch (call.method) {
      case 'appendEvent':
        if (args is Map) {
          events.insert(0, <String, Object?>{
            'at': isoWithOffset(now()),
            'kind': args['kind'],
            'data': args['data'],
          });
        }
        return null;
      case 'readEvents':
        return jsonEncode(events);
      case 'enforcementState':
        return state;
      case 'escapeToday':
        return escapeResult;
    }
    return null;
  }
}

/// A native `enforcementState` map; Thursday 2026-10-01, alarm 07:00.
Map<String, Object?> nativeState({
  String today = '2026-10-01',
  int? alarmHour = 7,
  int? alarmMinute = 0,
  bool dismissedToday = false,
  bool escapedToday = false,
  bool freeToday = false,
  bool freeTomorrow = false,
  int streak = 0,
  String? lockedThrough,
  String? lastMiss,
  String? updatedAt,
  String? lockIfMissToday = '2026-10-02',
  String? lockIfMissTomorrow = '2026-10-03',
}) => <String, Object?>{
  'today': today,
  'alarmHour': alarmHour,
  'alarmMinute': alarmMinute,
  'dismissedToday': dismissedToday,
  'escapedToday': escapedToday,
  'freeToday': freeToday,
  'freeTomorrow': freeTomorrow,
  'streak': streak,
  'lockedThrough': lockedThrough,
  'lastMiss': lastMiss,
  'updatedAt': updatedAt,
  'lockIfMissToday': lockIfMissToday,
  'lockIfMissTomorrow': lockIfMissTomorrow,
};
