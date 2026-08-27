import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('an unconfigured install registers neither proof', () async {
    final settings = await RoomProofSettings.load();
    expect(settings.nfcTagId, isNull);
    expect(settings.qrPayload, isNull);
  });

  test('a saved NFC tag round-trips', () async {
    await RoomProofSettings.saveNfcTag('04a2b3c4');
    expect((await RoomProofSettings.load()).nfcTagId, '04a2b3c4');
  });

  test('a saved QR payload round-trips', () async {
    await RoomProofSettings.saveQrPayload('kitchen');
    expect((await RoomProofSettings.load()).qrPayload, 'kitchen');
  });

  test('the two proofs are stored independently', () async {
    await RoomProofSettings.saveNfcTag('04a2b3c4');
    await RoomProofSettings.saveQrPayload('kitchen');
    final settings = await RoomProofSettings.load();
    expect(settings.nfcTagId, '04a2b3c4');
    expect(settings.qrPayload, 'kitchen');
  });
}
