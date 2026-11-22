import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/enforcement_publish.dart';
import 'package:wake_alarm_sync/services/headless_ring_start.dart';
import 'package:wake_alarm_sync/services/session_handoff.dart';

/// A bypass and a dismiss reach the PC at once, not at the next sync
/// (2026-11-22): the PC rings for a bypass until it sees a newer dismiss.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<String> calls;

  setUp(() {
    calls = <String>[];
    SharedPreferences.setMockInitialValues(<String, Object>{});
    for (final name in [headlessChannelName, AlarmScheduler.channelName]) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(MethodChannel(name), (call) async {
            calls.add(call.method);
            return null;
          });
    }
  });

  test('the headless publish pushes once, then says done', () async {
    var published = 0;
    await runHeadlessPublish(
      publish: () async {
        published++;
        return true;
      },
    );
    expect(published, 1);
    expect(calls, ['done']);
  });

  test('done is sent even when the publish blows up', () async {
    await expectLater(
      runHeadlessPublish(publish: () async => throw StateError('boom')),
      throwsStateError,
    );
    expect(calls, ['done']);
  });

  test('with no sync backend nothing is pushed', () async {
    expect(await publishEnforcementNow(), isFalse);
  });

  test('a dismiss publishes at once, after telling native', () async {
    final order = <String>[];
    final handoff = SessionHandoff(
      scheduler: AlarmScheduler(),
      now: () => DateTime(2026, 11, 22, 7, 40),
      publishNow: () async {
        order
          ..addAll(calls)
          ..add('publish');
        return true;
      },
    );
    await handoff.afterDismiss(away: true);
    expect(order, ['markRingDismissed', 'publish']);
  });
}
