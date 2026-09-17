import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<MethodCall> calls;
  late AlarmScheduler scheduler;
  Object? reply;

  setUp(() {
    calls = <MethodCall>[];
    reply = null;
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          return reply;
        });
    scheduler = AlarmScheduler(channel: channel);
  });

  test('schedule passes hour and minute across the channel', () async {
    await scheduler.schedule(6, 45);
    expect(calls.single.method, 'schedule');
    expect(calls.single.arguments, <String, int>{'hour': 6, 'minute': 45});
  });

  test('there is no way to cancel the alarm', () {
    // Not a missing wrapper: the Kotlin handler is gone too, so the alarm
    // genuinely cannot be switched off from the app. The only way past it is
    // the full dismiss ritual at ring time.
    expect(
      calls.where((c) => c.method == 'cancel'),
      isEmpty,
      reason: 'no code path may invoke cancel',
    );
  });

  test('armSchedule passes the policy time across the channel', () async {
    await scheduler.armSchedule(8, 0);
    expect(calls.single.method, 'armSchedule');
    expect(calls.single.arguments, <String, int>{'hour': 8, 'minute': 0});
  });

  test('dismiss invokes dismiss', () async {
    await scheduler.dismiss();
    expect(calls.single.method, 'dismiss');
  });

  test('rearm returns the platform result', () async {
    reply = true;
    expect(await scheduler.rearm(), isTrue);
  });

  test('rearm treats a null platform result as "nothing armed"', () async {
    expect(await scheduler.rearm(), isFalse);
  });

  test('canUseFullScreenIntent returns the platform result', () async {
    reply = true;
    expect(await scheduler.canUseFullScreenIntent(), isTrue);
  });

  test('canUseFullScreenIntent fails closed on a null result', () async {
    expect(await scheduler.canUseFullScreenIntent(), isFalse);
  });

  test('beginStepCount invokes beginStepCount', () async {
    await scheduler.beginStepCount();
    expect(calls.single.method, 'beginStepCount');
  });

  test('stepsSinceRingStart returns the platform count', () async {
    reply = 31;
    expect(await scheduler.stepsSinceRingStart(), 31);
  });

  test('stepsSinceRingStart reports -1 when the platform gives null', () async {
    expect(await scheduler.stepsSinceRingStart(), -1);
  });

  test('updateSessionNotice carries date, label and the deadline', () async {
    final at = DateTime(2026, 9, 17, 8, 45);
    await scheduler.updateSessionNotice(
      date: '2026-09-17',
      label: 'Tap the bathroom tag',
      deadline: at,
    );
    expect(calls.single.method, 'updateSessionNotice');
    expect(calls.single.arguments, <String, Object?>{
      'date': '2026-09-17',
      'label': 'Tap the bathroom tag',
      'deadlineMillis': at.millisecondsSinceEpoch,
    });
  });

  test('updateSessionNotice sends null for a leg with no deadline', () async {
    await scheduler.updateSessionNotice(date: '2026-09-17', label: 'x');
    expect(
      (calls.single.arguments as Map<Object?, Object?>)['deadlineMillis'],
      isNull,
    );
  });

  test('morningLive and isRinging fail closed on a null result', () async {
    expect(await scheduler.morningLive(), isFalse);
    expect(await scheduler.isRinging(), isFalse);
    reply = true;
    expect(await scheduler.morningLive(), isTrue);
    expect(await scheduler.isRinging(), isTrue);
  });
}
