import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Locally-stored GitHub sync configuration for wake_alarm_sync.
///
/// The GitHub token is kept in the OS keystore (Android Keystore) via
/// [FlutterSecureStorage]; the Gist ID (not a secret) lives in
/// `SharedPreferences`. Legacy builds stored the token in plaintext
/// prefs; [load]/[save] migrate it transparently and never drop the
/// plaintext copy until a secure write is confirmed.
class SyncSettings {
  /// Creates a [SyncSettings].
  const SyncSettings({required this.token, required this.gistId});

  /// GitHub access token (PAT or device-flow token).
  final String token;

  /// ID of the private Gist used to sync the alarm time.
  final String gistId;

  /// Baked-in OAuth App client ID for the device-flow "Connect" button.
  /// Device-flow client IDs are public identifiers, not secrets.
  static const defaultClientId = 'Ov23liGUPrPe1FFRSel6';

  /// True when both token and gist ID are present and sync can proceed.
  bool get isConfigured => token.isNotEmpty && gistId.isNotEmpty;

  // Legacy plaintext key — read-only; removed once migrated to keystore.
  static const _kLegacyToken = 'github_token';
  static const _kGistId = 'gist_id';
  static const _secureTokenKey = 'github_token';

  static const _secure = FlutterSecureStorage();

  /// Loads settings from persistent storage.
  static Future<SyncSettings> load() async {
    final prefs = await SharedPreferences.getInstance();
    return SyncSettings(
      token: await _loadToken(prefs),
      gistId: prefs.getString(_kGistId) ?? '',
    );
  }

  /// Reads the token from the keystore, falling back to the legacy
  /// plaintext value. A legacy value is migrated into the keystore on
  /// read, but only deleted from prefs once that write succeeds.
  static Future<String> _loadToken(SharedPreferences prefs) async {
    String? secure;
    try {
      secure = await _secure.read(key: _secureTokenKey);
    } on Exception catch (_) {
      secure = null;
    }
    if (secure != null && secure.isNotEmpty) return secure;

    final legacy = prefs.getString(_kLegacyToken) ?? '';
    if (legacy.isNotEmpty && await _writeSecureToken(legacy)) {
      await prefs.remove(_kLegacyToken);
    }
    return legacy;
  }

  /// Persists current settings.
  Future<void> save() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kGistId, gistId);
    if (await _writeSecureToken(token)) {
      await prefs.remove(_kLegacyToken);
    } else {
      await prefs.setString(_kLegacyToken, token);
    }
  }

  /// Removes all stored credentials.
  static Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kGistId);
    await prefs.remove(_kLegacyToken);
    await _writeSecureToken('');
  }

  /// Writes [token] to the keystore. Returns false if the platform
  /// secret service is unavailable.
  static Future<bool> _writeSecureToken(String token) async {
    try {
      if (token.isEmpty) {
        await _secure.delete(key: _secureTokenKey);
      } else {
        await _secure.write(key: _secureTokenKey, value: token);
      }
      return true;
    } on Exception catch (_) {
      return false;
    }
  }

  /// Returns a copy with optional field overrides.
  SyncSettings copyWith({String? token, String? gistId}) {
    return SyncSettings(
      token: token ?? this.token,
      gistId: gistId ?? this.gistId,
    );
  }
}
