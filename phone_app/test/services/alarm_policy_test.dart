import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_policy.dart';

/// Every test pins "now": the baseline is the ramp, so an unpinned test that
/// passes at 08:00 today fails at 07:59 tomorrow.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Evening of the ramp's first day: the next alarm is 2026-09-26, 07:59.
  final evening = DateTime(2026, 9, 25, 22);

  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  String hm(AlarmPolicy p) =>
      '${p.hour.toString().padLeft(2, '0')}:'
      '${p.minute.toString().padLeft(2, '0')}';

  test('armed the evening before, it uses the day it fires on', () async {
    // The whole point of evaluating the fire day: arming at 22:00 on the last
    // 08:00 day must already give tomorrow's 07:59, or the phone would ring
    // at yesterday's time every single day.
    final policy = await AlarmPolicy.load(now: evening);
    expect(hm(policy), '07:59');
    expect(policy.isOverridden, isFalse);
  });

  test('before the alarm on its own day, it is still today', () {
    final policy = AlarmPolicy.resolve(DateTime(2026, 10, 5, 3), null);
    expect(hm(policy), '07:50');
  });

  test('once today has fired, it is tomorrow', () {
    final policy = AlarmPolicy.resolve(DateTime(2026, 10, 5, 7, 50), null);
    expect(hm(policy), '07:49');
  });

  test('past the floor it stays at 07:00', () {
    expect(hm(AlarmPolicy.resolve(DateTime(2027, 3, 1, 12), null)), '07:00');
  });

  test('an earlier time is accepted and applied', () async {
    expect(await AlarmPolicy.setEarlier(6, 30, now: evening), isTrue);
    final policy = await AlarmPolicy.load(now: evening);
    expect(hm(policy), '06:30');
    expect(policy.isOverridden, isTrue);
    expect(policy.baselineHour * 60 + policy.baselineMinute, 7 * 60 + 59);
  });

  test('a later time is refused', () async {
    expect(await AlarmPolicy.setEarlier(9, 0, now: evening), isFalse);
    expect(hm(await AlarmPolicy.load(now: evening)), '07:59');
  });

  test('the ramp baseline itself is not an "earlier" time', () async {
    expect(await AlarmPolicy.setEarlier(7, 59, now: evening), isFalse);
    // 08:00 was the baseline yesterday; it is a minute late now.
    expect(await AlarmPolicy.setEarlier(8, 0, now: evening), isFalse);
    expect(await AlarmPolicy.setEarlier(7, 58, now: evening), isTrue);
  });

  test('an active override can only ratchet further down', () async {
    await AlarmPolicy.setEarlier(6, 0, now: evening);
    // 07:00 is earlier than the 07:59 baseline but LATER than the active
    // 06:00 override, so accepting it would buy the user an hour of sleep.
    expect(await AlarmPolicy.setEarlier(7, 0, now: evening), isFalse);
    expect(hm(await AlarmPolicy.load(now: evening)), '06:00');
    expect(await AlarmPolicy.setEarlier(5, 30, now: evening), isTrue);
    expect(hm(await AlarmPolicy.load(now: evening)), '05:30');
  });

  test('firing resets to the baseline (one-shot)', () async {
    await AlarmPolicy.setEarlier(5, 0, now: evening);
    await AlarmPolicy.resetAfterFire();
    final policy = await AlarmPolicy.load(now: evening);
    expect(hm(policy), '07:59');
    expect(policy.isOverridden, isFalse);
  });

  test('a stored value later than the baseline is ignored', () async {
    // The prefs store is not a trust boundary: a value that would weaken the
    // alarm must be rejected on read as well as on write.
    SharedPreferences.setMockInitialValues(<String, Object>{
      AlarmPolicy.kOverrideKey: 23 * 60,
    });
    final policy = await AlarmPolicy.load(now: evening);
    expect(hm(policy), '07:59');
    expect(policy.isOverridden, isFalse);
  });

  test('an override the ramp has caught up with lapses', () {
    // 07:45 was an early start in September; by 2026-10-20 the ramp itself
    // is 07:35, so the stale override would be a *later* alarm.
    final policy = AlarmPolicy.resolve(DateTime(2026, 10, 19, 22), 7 * 60 + 45);
    expect(hm(policy), '07:35');
    expect(policy.isOverridden, isFalse);
  });

  test('without a clock it resolves against now', () async {
    final policy = await AlarmPolicy.load();
    expect(policy.hour * 60 + policy.minute, lessThanOrEqualTo(8 * 60));
  });
}
