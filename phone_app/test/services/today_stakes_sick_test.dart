import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/enforcement_state.dart';
import 'package:wake_alarm_sync/services/today_stakes.dart';

import '../fake_enforcement_channel.dart';

/// 2026-10-01 is a Thursday: a stick day unless it is sick.
EnforcementState _state({bool sickToday = false, bool sickTomorrow = false}) =>
    EnforcementState.fromMap({
      ...nativeState(),
      'sickToday': sickToday,
      'sickTomorrow': sickTomorrow,
    })!;

void main() {
  final thuMorning = DateTime(2026, 10, 1, 6, 50);

  test('the native sick flags are parsed, defaulting to false', () {
    final state = _state(sickToday: true);
    expect(state.sickToday, isTrue);
    expect(state.sickTomorrow, isFalse);
    expect(EnforcementState.fromMap(nativeState())!.sickToday, isFalse);
  });

  test('a sick stick day promises no lockdown and no PC ring', () {
    final view = describeStakes(
      now: thuMorning,
      state: _state(sickToday: true),
    );
    expect(view.title, 'Today · Thu 1 Oct — sick day');
    expect(view.stakes, ['Sick day — no alarm, nothing at stake.']);
  });

  test("tomorrow's sick day is announced after today's alarm", () {
    final evening = DateTime(2026, 10, 1, 20);
    final view = describeStakes(
      now: evening,
      state: _state(sickTomorrow: true),
    );
    expect(view.title, 'Tomorrow · Fri 2 Oct — sick day');
    expect(view.stakes, ['Sick day — no alarm, nothing at stake.']);
  });

  test('the ring line is silent on a sick day', () {
    expect(ringStakesLine(_state()), isNotNull);
    expect(ringStakesLine(_state(sickToday: true)), isNull);
  });
}
