import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

MorningSession session(DateTime at, {double? kg}) => SessionRules.start(
  now: at,
  tags: const SessionTagSettings(),
  nfcAvailable: false,
)..weightKg = kg;

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('saves and reloads the live session', () async {
    final store = SessionStore();
    expect(await store.loadCurrent(), isNull);
    await store.save(session(DateTime(2026, 9, 17, 8), kg: 72));
    final back = await store.loadCurrent();
    expect(back?.date, '2026-09-17');
    expect(back?.weightKg, 72);
  });

  test('archive moves it into the history, newest first', () async {
    final store = SessionStore();
    await store.archive(session(DateTime(2026, 9, 16, 8), kg: 71));
    await store.archive(session(DateTime(2026, 9, 17, 8)));
    await store.save(session(DateTime(2026, 9, 18, 8)));
    await store.archive((await store.loadCurrent())!);
    final history = await store.history();
    expect(history.map((s) => s.date), <String>[
      '2026-09-18',
      '2026-09-17',
      '2026-09-16',
    ]);
    expect(await store.loadCurrent(), isNull);
    expect(await store.lastWeightKg(), 71);
  });

  test('a second session on one date replaces the first', () async {
    final store = SessionStore();
    await store.archive(session(DateTime(2026, 9, 17, 8), kg: 70));
    await store.archive(session(DateTime(2026, 9, 17, 9), kg: 72));
    final history = await store.history();
    expect(history, hasLength(1));
    expect(history.single.weightKg, 72);
  });

  test('keeps only the newest thirty', () async {
    final store = SessionStore();
    for (var day = 1; day <= 32; day++) {
      await store.archive(session(DateTime(2026, 1, day, 8)));
    }
    expect(await store.history(), hasLength(SessionStore.keep));
  });

  test('merge takes the newer copy per date', () async {
    final store = SessionStore();
    final local = session(DateTime(2026, 9, 17, 8), kg: 70);
    await store.archive(local);
    final older = session(DateTime(2026, 9, 17, 8), kg: 99)
      ..updatedAt = local.updatedAt.subtract(const Duration(hours: 1));
    expect(await store.mergeHistory(<MorningSession>[older]), isFalse);
    final newer = session(DateTime(2026, 9, 17, 8), kg: 72)
      ..updatedAt = local.updatedAt.add(const Duration(hours: 1));
    final other = session(DateTime(2026, 9, 10, 8), kg: 68);
    expect(await store.mergeHistory(<MorningSession>[newer, other]), isTrue);
    final history = await store.history();
    expect(history.map((s) => s.date), <String>['2026-09-17', '2026-09-10']);
    expect(history.first.weightKg, 72);
  });

  test('malformed storage reads as empty', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      SessionStore.kCurrentKey: '{oops',
      SessionStore.kHistoryKey: '[1, "x", {}]',
    });
    final store = SessionStore();
    expect(await store.loadCurrent(), isNull);
    expect(await store.history(), isEmpty);
    expect(SessionStore.decodeHistory('nope'), isEmpty);
    expect(SessionStore.decodeSessions('not a list'), isEmpty);
  });
}
