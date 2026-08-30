import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('an unconfigured install registers no tags', () async {
    final settings = await RoomProofSettings.load();
    expect(settings.tagAt(0), isNull);
    expect(settings.tagAt(1), isNull);
    expect(settings.isComplete, isFalse);
  });

  test('each slot round-trips independently', () async {
    await RoomProofSettings.saveNfcTagAt(0, '04a2b3c4');
    expect((await RoomProofSettings.load()).tagAt(0), '04a2b3c4');
    expect((await RoomProofSettings.load()).tagAt(1), isNull);

    await RoomProofSettings.saveNfcTagAt(1, '04ffee11');
    final both = await RoomProofSettings.load();
    expect(both.tagAt(0), '04a2b3c4', reason: 'slot 0 must survive');
    expect(both.tagAt(1), '04ffee11');
    expect(both.isComplete, isTrue);
  });

  test('re-registering one slot leaves the other alone', () async {
    await RoomProofSettings.saveNfcTagAt(0, 'aaa');
    await RoomProofSettings.saveNfcTagAt(1, 'bbb');
    await RoomProofSettings.saveNfcTagAt(0, 'ccc');
    final settings = await RoomProofSettings.load();
    expect(settings.tagAt(0), 'ccc');
    expect(settings.tagAt(1), 'bbb');
  });

  test('a legacy single tag migrates into slot 1', () async {
    // An existing install has one tag under the pre-two-tag key. Losing it
    // would leave the user bypass-only on the first morning after updating.
    SharedPreferences.setMockInitialValues(<String, Object>{
      RoomProofSettings.kLegacyNfcTagKey: '0465dab3ce2a81',
    });
    final settings = await RoomProofSettings.load();
    expect(settings.tagAt(0), '0465dab3ce2a81');
    expect(settings.tagAt(1), isNull);
    expect(settings.isComplete, isFalse);
  });

  test('the same tag in both slots is not a complete configuration', () async {
    // One physical tag satisfying both stages would remove the walk.
    await RoomProofSettings.saveNfcTagAt(0, 'same');
    await RoomProofSettings.saveNfcTagAt(1, 'same');
    expect((await RoomProofSettings.load()).isComplete, isFalse);
  });

  test('a malformed stored value degrades to unregistered', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      RoomProofSettings.kNfcTagsKey: 'not json',
    });
    final settings = await RoomProofSettings.load();
    expect(settings.tagAt(0), isNull);
    expect(settings.isComplete, isFalse);
  });

  test('an out-of-range slot write is ignored', () async {
    await RoomProofSettings.saveNfcTagAt(5, 'nope');
    expect((await RoomProofSettings.load()).isComplete, isFalse);
  });
}
