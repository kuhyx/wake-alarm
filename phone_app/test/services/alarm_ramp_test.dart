import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/alarm_ramp.dart';

String _fmt(int minutes) =>
    '${(minutes ~/ 60).toString().padLeft(2, '0')}:'
    '${(minutes % 60).toString().padLeft(2, '0')}';

String _on(int y, int m, int d, [Set<String> earned = const {}]) =>
    _fmt(rampMinutesOn(DateTime(y, m, d), earned));

void main() {
  test('the seeds reproduce what already rang: 07:59, 07:58, then 07:57', () {
    expect(_on(2026, 9, 25), '08:00'); // Fri: nothing earned before it
    expect(_on(2026, 9, 26), '07:59'); // Sat
    expect(_on(2026, 9, 27), '07:58'); // Sun
    expect(_on(2026, 9, 28), '07:57'); // Mon
  });

  test('workdays hold the latest non-workday time', () {
    final earned = {'2026-09-28'}; // Monday dismissed
    expect(_on(2026, 9, 29, earned), '07:57'); // Tue
    expect(_on(2026, 9, 30, earned), '07:57'); // Wed
    expect(_on(2026, 10, 1, earned), '07:57'); // Thu
    expect(_on(2026, 10, 2, earned), '07:56'); // Fri: Monday's minute
  });

  test('no earned minute (a miss or a free day) means no step', () {
    // Friday missed: Saturday rings at Friday's time.
    final earned = {'2026-09-28'};
    expect(_on(2026, 10, 3, earned), '07:56');
    // Saturday dismissed, Sunday free (never rings, earns nothing):
    earned.add('2026-10-03');
    expect(_on(2026, 10, 4, earned), '07:55');
    expect(_on(2026, 10, 5, earned), '07:55');
  });

  test('a workday date in the set earns nothing', () {
    expect(_on(2026, 10, 2, {'2026-09-29', '2026-09-30'}), '07:57');
  });

  test('unparseable keys are ignored', () {
    expect(_on(2026, 10, 2, {'nonsense', ''}), '07:57');
  });

  test('07:00 is the floor', () {
    final earned = {
      for (var i = 0; i < 200; i++) rampDateKey(DateTime(2026, 10, 2 + i)),
    };
    expect(_on(2027, 12, 31, earned), '07:00');
  });

  test('only the date matters, not the time of day', () {
    expect(
      rampMinutesOn(DateTime(2026, 9, 26, 23, 59), const {}),
      rampMinutesOn(DateTime(2026, 9, 26), const {}),
    );
  });

  test('the workday set is Tue/Wed/Thu', () {
    expect(workdays, {DateTime.tuesday, DateTime.wednesday, DateTime.thursday});
    expect(isWorkday(DateTime(2026, 9, 29)), isTrue);
    expect(isWorkday(DateTime(2026, 9, 28)), isFalse);
  });

  test('date keys are zero-padded ISO dates', () {
    expect(rampDateKey(DateTime(2026, 3, 4, 23)), '2026-03-04');
  });
}
