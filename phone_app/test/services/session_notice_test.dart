import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_notice.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

final DateTime t0 = DateTime(2026, 9, 17, 8, 5);
const SessionTagSettings allTags = SessionTagSettings(
  tagIds: <String>['bath', 'ward', 'desk'],
);

MorningSession fresh() =>
    SessionRules.start(now: t0, tags: allTags, nfcAvailable: true);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<MethodCall> calls;
  late AlarmScheduler scheduler;

  setUp(() {
    calls = <MethodCall>[];
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          return null;
        });
    scheduler = AlarmScheduler(channel: channel);
  });

  test('the label is the live leg', () {
    expect(noticeLabel(fresh()), 'Tap the bathroom tag');
  });

  test('a leg whose re-ring is spent says it will pass by itself', () {
    final s = fresh()..deadlineRung.add(SessionLeg.bathroomIn);
    expect(noticeLabel(s), 'Tap the bathroom tag — passes by itself soon');
  });

  test('a finished session drops the deadline and posts no notice', () async {
    final s = fresh()
      ..enterCheckIn(72, 3, t0)
      ..onTag(SessionTagSlot.bathroom, t0)
      ..onTag(SessionTagSlot.bathroom, t0.add(const Duration(minutes: 9)))
      ..onTag(SessionTagSlot.wardrobe, t0)
      ..onTag(SessionTagSlot.desk, t0);
    expect(s.isActive, isFalse);
    await pointNativeAtLeg(scheduler, s);
    expect(calls.map((c) => c.method), <String>['armReRing']);
    expect(calls.single.arguments, <String, int?>{'atMillis': null});
  });

  test('pointNativeAtLeg arms the deadline and the notice together', () async {
    final s = fresh();
    await pointNativeAtLeg(scheduler, s);
    expect(calls.map((c) => c.method), <String>[
      'armReRing',
      'updateSessionNotice',
    ]);
    final deadline = s.nextDeadline()!.millisecondsSinceEpoch;
    expect(calls[0].arguments, <String, int?>{'atMillis': deadline});
    expect(calls[1].arguments, <String, Object?>{
      'date': '2026-09-17',
      'label': 'Tap the bathroom tag',
      'deadlineMillis': deadline,
    });
  });

  test('a spent re-ring sends no deadline to either side', () async {
    final s = fresh()..deadlineRung.add(SessionLeg.bathroomIn);
    await pointNativeAtLeg(scheduler, s);
    expect(calls[0].arguments, <String, int?>{'atMillis': null});
    expect(
      (calls[1].arguments as Map<Object?, Object?>)['deadlineMillis'],
      isNull,
    );
  });
}
