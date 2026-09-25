import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/alarm_ramp.dart';

String _fmt(int minutes) =>
    '${(minutes ~/ 60).toString().padLeft(2, '0')}:'
    '${(minutes % 60).toString().padLeft(2, '0')}';

void main() {
  test('the ramp: 08:00, a minute a day, then 07:00 for good', () {
    final cases = <DateTime, String>{
      DateTime(2026): '08:00',
      DateTime(2026, 9, 25): '08:00',
      DateTime(2026, 9, 26): '07:59',
      DateTime(2026, 10, 5): '07:50',
      DateTime(2026, 11, 23): '07:01',
      DateTime(2026, 11, 24): '07:00',
      DateTime(2026, 11, 25): '07:00',
      DateTime(2030, 6): '07:00',
    };
    for (final MapEntry(key: day, value: expected) in cases.entries) {
      expect(_fmt(rampMinutesOn(day)), expected, reason: '$day');
    }
  });

  test('only the date matters, not the time of day', () {
    expect(
      rampMinutesOn(DateTime(2026, 9, 26, 23, 59)),
      rampMinutesOn(DateTime(2026, 9, 26)),
    );
  });

  test('the DST change on 2026-10-25 costs exactly one minute a day', () {
    // Local midnights either side of the fall-back are 25 hours apart; a
    // Duration-based count would see 0 or 2 days somewhere around here.
    expect(_fmt(rampMinutesOn(DateTime(2026, 10, 24, 23, 30))), '07:31');
    expect(_fmt(rampMinutesOn(DateTime(2026, 10, 25, 0, 30))), '07:30');
    expect(_fmt(rampMinutesOn(DateTime(2026, 10, 26, 0, 30))), '07:29');
  });

  test('never moves later from one day to the next', () {
    var previous = rampStartMinutes;
    for (var n = -5; n < 90; n++) {
      final minutes = rampMinutesOn(DateTime(2026, 9, 25 + n));
      expect(minutes, lessThanOrEqualTo(previous));
      expect(minutes, greaterThanOrEqualTo(rampFloorMinutes));
      previous = minutes;
    }
  });
}
