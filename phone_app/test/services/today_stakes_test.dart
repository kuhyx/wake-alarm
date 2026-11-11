import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/enforcement_state.dart';
import 'package:wake_alarm_sync/services/today_stakes.dart';

import '../fake_enforcement_channel.dart';

EnforcementState _state({
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
  String? lockIfMissToday = '2026-10-02',
  String? lockIfMissTomorrow = '2026-10-03',
}) => EnforcementState.fromMap(
  nativeState(
    today: today,
    alarmHour: alarmHour,
    alarmMinute: alarmMinute,
    dismissedToday: dismissedToday,
    escapedToday: escapedToday,
    freeToday: freeToday,
    freeTomorrow: freeTomorrow,
    streak: streak,
    lockedThrough: lockedThrough,
    lastMiss: lastMiss,
    lockIfMissToday: lockIfMissToday,
    lockIfMissTomorrow: lockIfMissTomorrow,
  ),
)!;

void main() {
  // 2026-10-01 is a Thursday (stick day), 2026-10-02 a Friday (carrot day).
  final thuMorning = DateTime(2026, 10, 1, 6, 50);

  group('describeStakes', () {
    test('a stick day before A + 15 states the miss and the PC ring', () {
      final view = describeStakes(now: thuMorning, state: _state());
      expect(view.title, 'Today · Thu 1 Oct — stick day');
      const miss =
          'Miss (no dismiss by 07:15) → apps locked through Fri 2 Oct + '
          "tomorrow's PC leniency gone";
      expect(view.stakes, [
        miss,
        'PC rings at 07:02 if the phone is silent (up to 30 min)',
      ]);
      expect(view.pending, isEmpty);
      expect(view.streak, 'Streak: 0 missed stick days in a row');
    });

    test('a dismissed morning moves on to tomorrow, with its own time', () {
      final view = describeStakes(
        now: DateTime(2026, 10, 1, 7, 5),
        state: _state(dismissedToday: true),
        nextAlarm: (hour: 6, minute: 59),
      );
      expect(view.title, 'Tomorrow · Fri 2 Oct — carrot day');
      expect(view.stakes, [
        'Finish the morning by 08:29 → PC open until 11:00',
        'PC rings at 07:01 if the phone is silent (up to 30 min)',
      ]);
    });

    test('past A + 15 is tomorrow too, even without a dismiss', () {
      final view = describeStakes(
        now: DateTime(2026, 9, 30, 20),
        state: _state(today: '2026-09-30'),
      );
      // Wednesday evening: Thursday is a stick day, judged by the next day.
      expect(view.title, 'Tomorrow · Thu 1 Oct — stick day');
      expect(view.stakes.first, contains('locked through Sat 3 Oct'));
      expect(view.stakes.first, contains("Fri's PC leniency gone"));
    });

    test('an escaped morning is no longer open', () {
      final view = describeStakes(
        now: thuMorning,
        state: _state(escapedToday: true),
      );
      expect(view.title, startsWith('Tomorrow'));
      expect(view.pending, ['This morning is excused ("That was a bug").']);
    });

    test('a free day has nothing at stake', () {
      final view = describeStakes(
        now: thuMorning,
        state: _state(freeToday: true),
      );
      expect(view.title, 'Today · Thu 1 Oct — free day');
      expect(view.stakes, ['Free day — no alarm, nothing at stake.']);
    });

    test('tomorrow being free is read from the tomorrow flag', () {
      final view = describeStakes(
        now: DateTime(2026, 10, 1, 20),
        state: _state(freeTomorrow: true),
      );
      expect(view.title, 'Tomorrow · Fri 2 Oct — free day');
    });

    test('no alarm at all says so instead of inventing a time', () {
      final view = describeStakes(
        now: thuMorning,
        state: _state(alarmHour: null, alarmMinute: null),
      );
      expect(view.title, startsWith('Tomorrow'));
      expect(view.stakes, ['No alarm armed yet — nothing at stake.']);
    });

    test('a missing native lock date falls back to the next day', () {
      final view = describeStakes(
        now: thuMorning,
        state: _state(lockIfMissToday: null),
      );
      expect(view.stakes.first, contains('locked through Fri 2 Oct'));
    });

    test('a lockdown in force and a miss today are pending', () {
      final view = describeStakes(
        now: DateTime(2026, 10, 1, 9),
        state: _state(
          streak: 2,
          lockedThrough: '2026-10-03',
          lastMiss: '2026-10-01',
        ),
      );
      expect(view.pending, [
        'Apps locked through Sat 3 Oct.',
        "Missed this morning → tomorrow's PC leniency is gone.",
      ]);
      expect(view.streak, 'Streak: 2 missed stick days in a row');
    });

    test('a lockdown that has ended is not pending; one miss is singular', () {
      final view = describeStakes(
        now: DateTime(2026, 10, 1, 9),
        state: _state(streak: 1, lockedThrough: '2026-09-30'),
      );
      expect(view.pending, isEmpty);
      expect(view.streak, 'Streak: 1 missed stick day in a row');
    });
  });

  group('ringStakesLine', () {
    test('an open stick-day ring names the cost of not dismissing', () {
      expect(
        ringStakesLine(_state()),
        'Stick day: no dismiss by 07:15 → apps locked through Fri 2 Oct',
      );
    });

    test('a missing native lock date falls back to the next day', () {
      expect(
        ringStakesLine(_state(lockIfMissToday: null)),
        contains('Fri 2 Oct'),
      );
    });

    test('nothing on a carrot, free, settled or alarm-less day', () {
      expect(ringStakesLine(_state(today: '2026-10-02')), isNull);
      expect(ringStakesLine(_state(freeToday: true)), isNull);
      expect(ringStakesLine(_state(dismissedToday: true)), isNull);
      expect(ringStakesLine(_state(escapedToday: true)), isNull);
      expect(ringStakesLine(_state(lastMiss: '2026-10-01')), isNull);
      expect(ringStakesLine(_state(alarmHour: null)), isNull);
    });
  });

  group('ringStakes', () {
    test('an open stick-day ring returns deadline and lockdown', () {
      final stakes = ringStakes(_state());
      expect(stakes, isNotNull);
      expect(stakes!.by, DateTime(2026, 10, 1, 7, 15));
      expect(stakes.lockThrough, DateTime(2026, 10, 2));
    });

    test('a missing native lock date falls back to the next day', () {
      final stakes = ringStakes(_state(lockIfMissToday: null));
      expect(stakes, isNotNull);
      expect(stakes!.lockThrough, DateTime(2026, 10, 2));
    });

    test('nothing on a carrot, free, settled or alarm-less day', () {
      expect(ringStakes(_state(today: '2026-10-02')), isNull);
      expect(ringStakes(_state(freeToday: true)), isNull);
      expect(ringStakes(_state(dismissedToday: true)), isNull);
      expect(ringStakes(_state(escapedToday: true)), isNull);
      expect(ringStakes(_state(lastMiss: '2026-10-01')), isNull);
      expect(ringStakes(_state(alarmHour: null)), isNull);
    });
  });

  group('carrotCutoff', () {
    test('is A + 90 min before the cap, the cap after it', () {
      expect(
        carrotCutoff(DateTime(2026, 10, 2, 7)),
        DateTime(2026, 10, 2, 8, 30),
      );
      expect(
        carrotCutoff(DateTime(2026, 10, 2, 8, 15)),
        DateTime(2026, 10, 2, 9, 30),
      );
    });
  });

  test('formatDay and hhmm', () {
    expect(formatDay(DateTime(2026, 12, 31)), 'Thu 31 Dec');
    expect(hhmm(DateTime(2026, 1, 1, 6, 5)), '06:05');
  });
}
