import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/screens/sick_day_sheet.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';

import 'fake_day_pool_store.dart';

/// `applySickSheet` on its own: the free-day check holds even when the
/// screen's own pre-check is bypassed.
final _today = DateTime(2026, 10, 16);
final _day = DateTime(2026, 10, 20);
const SickSheetResult _mark = (action: SickSheetAction.mark, keep: {'diet'});

void main() {
  late SickDayPool sick;
  late FreeDayPool free;

  setUp(() async {
    sick = await SickDayPool.open(persistence: MemPersistence(), deviceId: 'p');
    free = await FreeDayPool.open(persistence: MemPersistence(), deviceId: 'p');
  });

  test('a mark with no free-day pool is refused', () async {
    await expectLater(
      applySickSheet(sick, _day, _mark, free: null, now: _today),
      throwsA(
        isA<SickDayPolicyError>().having(
          (e) => e.message,
          'message',
          contains('Free-day pool unavailable'),
        ),
      ),
    );
    expect(sick.isSick(_day), isFalse);
  });

  test('a mark on a free day is refused, naming the pool', () async {
    await free.mark(_day, now: _today);
    expect(freeDayRefusal(free, _day), contains('is a free day'));
    await expectLater(
      applySickSheet(sick, _day, _mark, free: free, now: _today),
      throwsA(isA<SickDayPolicyError>()),
    );
  });

  test('a mark keeps exactly the switched-on lockers', () async {
    expect(
      await applySickSheet(sick, _day, _mark, free: free, now: _today),
      isTrue,
    );
    expect(sick.keptLockers(_day), {'diet'});
    expect(keptLabel(sick.keptLockers(_day)), 'Diet');
  });
}
