import 'package:shared_preferences/shared_preferences.dart';

/// Persisted room-proof configuration: the registered NFC tag and QR payload.
///
/// Registering nothing means that mechanism cannot satisfy the proof — it does
/// not mean everything passes. See `RoomProof` for why redundancy matters.
class RoomProofSettings {
  /// Creates settings with the registered values, if any.
  const RoomProofSettings({this.nfcTagId, this.qrPayload});

  /// SharedPreferences key for the registered NFC tag id.
  static const String kNfcTagKey = 'roomProof.nfcTagId';

  /// SharedPreferences key for the expected QR payload.
  static const String kQrKey = 'roomProof.qrPayload';

  /// Lower-case hex id of the tag taped up in the other room.
  final String? nfcTagId;

  /// Text encoded in the printed QR code in the other room.
  final String? qrPayload;

  /// Loads the stored configuration.
  static Future<RoomProofSettings> load() async {
    final prefs = await SharedPreferences.getInstance();
    return RoomProofSettings(
      nfcTagId: prefs.getString(kNfcTagKey),
      qrPayload: prefs.getString(kQrKey),
    );
  }

  /// Stores [tagId] as the registered NFC tag.
  static Future<void> saveNfcTag(String tagId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(kNfcTagKey, tagId);
  }

  /// Stores [payload] as the expected QR code text.
  static Future<void> saveQrPayload(String payload) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(kQrKey, payload);
  }
}
