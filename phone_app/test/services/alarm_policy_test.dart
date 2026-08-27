import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_policy.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('a fresh install runs at the baseline', () async {
    final policy = await AlarmPolicy.load();
    expect(policy.hour, AlarmPolicy.baselineHour);
    expect(policy.minute, AlarmPolicy.baselineMinute);
    expect(policy.isOverridden, isFalse);
  });

  test('an earlier time is accepted and applied', () async {
    expect(await AlarmPolicy.setEarlier(6, 30), isTrue);
    final policy = await AlarmPolicy.load();
    expect(policy.hour, 6);
    expect(policy.minute, 30);
    expect(policy.isOverridden, isTrue);
  });

  test('a later time is refused', () async {
    expect(await AlarmPolicy.setEarlier(9, 0), isFalse);
    expect((await AlarmPolicy.load()).hour, AlarmPolicy.baselineHour);
  });

  test('the baseline itself is not an "earlier" time', () async {
    expect(
      await AlarmPolicy.setEarlier(
        AlarmPolicy.baselineHour,
        AlarmPolicy.baselineMinute,
      ),
      isFalse,
    );
  });

  test('an active override can only ratchet further down', () async {
    await AlarmPolicy.setEarlier(6, 0);
    // 07:00 is earlier than the 08:00 baseline but LATER than the active
    // 06:00 override, so accepting it would buy the user an hour of sleep.
    expect(await AlarmPolicy.setEarlier(7, 0), isFalse);
    expect((await AlarmPolicy.load()).hour, 6);
    expect(await AlarmPolicy.setEarlier(5, 30), isTrue);
    expect((await AlarmPolicy.load()).hour, 5);
  });

  test('firing resets to the baseline (one-shot)', () async {
    await AlarmPolicy.setEarlier(5, 0);
    await AlarmPolicy.resetAfterFire();
    final policy = await AlarmPolicy.load();
    expect(policy.hour, AlarmPolicy.baselineHour);
    expect(policy.isOverridden, isFalse);
  });

  test('a stored value later than the baseline is ignored', () async {
    // The prefs store is not a trust boundary: a value that would weaken the
    // alarm must be rejected on read as well as on write.
    SharedPreferences.setMockInitialValues(<String, Object>{
      AlarmPolicy.kOverrideKey: 23 * 60,
    });
    final policy = await AlarmPolicy.load();
    expect(policy.hour, AlarmPolicy.baselineHour);
    expect(policy.isOverridden, isFalse);
  });

  test('the baseline is 08:00', () async {
    expect(AlarmPolicy.baselineHour, 8);
    expect(AlarmPolicy.baselineMinute, 0);
  });
}
