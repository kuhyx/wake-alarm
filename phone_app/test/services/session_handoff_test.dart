import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_handoff.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final now = DateTime(2026, 9, 17, 8, 4);
  var hasNfc = true;

  setUp(() {
    hasNfc = true;
    SharedPreferences.setMockInitialValues(<String, Object>{});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel(AlarmScheduler.channelName),
          (call) async => call.method == 'hasNfc' ? hasNfc : null,
        );
  });

  SessionHandoff handoff() =>
      SessionHandoff(scheduler: AlarmScheduler(), now: () => now);

  test("the first dismiss starts today's session", () async {
    await SessionTagSettings.saveTagAt(SessionTagSlot.desk, 'd');
    expect(await handoff().afterDismiss(away: false), isTrue);
    final session = (await SessionStore().loadCurrent())!;
    expect(session.date, '2026-09-17');
    expect(session.startedAt, now);
    expect(session.reRings, 0);
    expect(session.passedHow[SessionLeg.dressed], LegPass.skipped);
    expect(session.passedHow.containsKey(SessionLeg.atDesk), isFalse);
  });

  test('without NFC the session is a bare weigh-in', () async {
    hasNfc = false;
    expect(await handoff().afterDismiss(away: false), isTrue);
    final session = (await SessionStore().loadCurrent())!;
    expect(session.bathroomTagRequired, isFalse);
  });

  test('away from home there is no session', () async {
    expect(await handoff().afterDismiss(away: true), isFalse);
    expect(await SessionStore().loadCurrent(), isNull);
  });

  test('a dismiss during a live session is a re-ring', () async {
    final store = SessionStore();
    await store.save(
      SessionRules.start(
        now: now.subtract(const Duration(minutes: 12)),
        tags: const SessionTagSettings(tagIds: <String>['b', 'w', 'd']),
        nfcAvailable: true,
      ),
    );
    expect(await handoff().afterDismiss(away: false), isTrue);
    final session = (await store.loadCurrent())!;
    expect(session.reRings, 1);
    expect(session.reRingReasons, <String>['deadline:bathroomIn']);
    expect(session.deadlineRung, <SessionLeg>{SessionLeg.bathroomIn});
  });

  test("a ring after today's session finished just closes", () async {
    final store = SessionStore();
    await store.save(
      SessionRules.start(
        now: now,
        tags: const SessionTagSettings(),
        nfcAvailable: false,
      )..outcome = SessionOutcome.completed,
    );
    expect(await handoff().afterDismiss(away: false), isFalse);
  });

  test("a ring after today's session was archived just closes", () async {
    final store = SessionStore();
    await store.archive(
      SessionRules.start(
        now: now.subtract(const Duration(minutes: 40)),
        tags: const SessionTagSettings(),
        nfcAvailable: false,
      )..outcome = SessionOutcome.completed,
    );
    expect(await handoff().afterDismiss(away: false), isFalse);
    expect(await store.loadCurrent(), isNull);
  });

  test("yesterday's unfinished session is archived as failed", () async {
    final store = SessionStore();
    await store.save(
      SessionRules.start(
        now: now.subtract(const Duration(days: 1)),
        tags: const SessionTagSettings(),
        nfcAvailable: false,
      ),
    );
    expect(await handoff().afterDismiss(away: false), isTrue);
    final history = await store.history();
    expect(history.single.date, '2026-09-16');
    expect(history.single.outcome, SessionOutcome.failed);
    expect((await store.loadCurrent())!.date, '2026-09-17');
  });
}
