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

  test('cancel invokes cancel', () async {
    await scheduler.cancel();
    expect(calls.single.method, 'cancel');
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
}
