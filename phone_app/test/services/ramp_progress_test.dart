import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/ramp_progress.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('a fresh install has earned nothing', () async {
    expect(await RampProgress.load(), isEmpty);
  });

  test('a dismissed non-workday morning earns its date, once', () async {
    expect(
      await RampProgress.recordDismiss(DateTime(2026, 9, 28, 7, 58)),
      isTrue,
    );
    expect(await RampProgress.recordDismiss(DateTime(2026, 9, 28, 9)), isFalse);
    expect(await RampProgress.load(), {'2026-09-28'});
  });

  test('a workday dismiss earns nothing', () async {
    expect(await RampProgress.recordDismiss(DateTime(2026, 9, 29, 8)), isFalse);
    expect(await RampProgress.load(), isEmpty);
  });

  test('merge is a union and drops non-canonical keys', () async {
    await RampProgress.merge({'2026-09-28'});
    expect(
      await RampProgress.merge({'2026-10-02', '2026-9-3', 'junk'}),
      isTrue,
    );
    expect(await RampProgress.merge({'2026-10-02'}), isFalse);
    expect(await RampProgress.load(), {'2026-09-28', '2026-10-02'});
  });

  test('corrupt storage reads as nothing earned', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      RampProgress.kEarnedKey: '{not json',
    });
    expect(await RampProgress.load(), isEmpty);
    SharedPreferences.setMockInitialValues(<String, Object>{
      RampProgress.kEarnedKey: '{"a": 1}',
    });
    expect(await RampProgress.load(), isEmpty);
  });
}
