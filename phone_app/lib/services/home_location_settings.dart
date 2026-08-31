import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Persisted home location: the Wi-Fi that means "home", plus a coordinate.
///
/// Registered from Settings by pressing capture once while at home. Nothing
/// is inferred and nothing is captured in the background.
///
/// **Unregistered is not "away".** An install that has never captured a home
/// keeps the full strict dismiss sequence; the geofence only starts
/// restricting once it has been told where home is. Treating unconfigured as
/// away would silently delete the whole NFC ritual on the first morning after
/// an update.
class HomeLocationSettings {
  /// Creates settings from stored values.
  const HomeLocationSettings({
    this.ssid,
    this.bssids = const <String>[],
    this.lat,
    this.lon,
    this.radiusMeters = defaultRadiusMeters,
  });

  /// SharedPreferences key holding the whole record as JSON.
  static const String kKey = 'homeLocation.value';

  /// How far from the stored coordinate still counts as home.
  static const double defaultRadiusMeters = 150;

  /// Network name of the home Wi-Fi, or null when none was captured.
  final String? ssid;

  /// Every access-point address seen at home, lowercased.
  ///
  /// A list, not a single value: a dual-band router answers to a different
  /// BSSID per band and a mesh node one per box, and the phone roams between
  /// them overnight. One stored address would call a band switch "travelling".
  final List<String> bssids;

  /// Latitude of the captured home, or null when none was captured.
  final double? lat;

  /// Longitude of the captured home, or null when none was captured.
  final double? lon;

  /// Radius around ([lat], [lon]) that counts as home.
  final double radiusMeters;

  /// Whether a home has ever been captured.
  bool get isConfigured => ssid != null || bssids.isNotEmpty || hasCoordinate;

  /// Whether a coordinate is stored, so the GPS fallback can be used.
  bool get hasCoordinate => lat != null && lon != null;

  /// Whether [ssid]/[bssid] identify the home network.
  ///
  /// Either signal is enough. The SSID survives roaming between bands and
  /// mesh nodes; the BSSID list is the stricter check for a captured AP.
  bool matchesWifi({String? ssid, String? bssid}) {
    if (ssid != null && ssid == this.ssid) return true;
    return bssid != null && bssids.contains(bssid.toLowerCase());
  }

  /// Loads the stored home; anything malformed reads as unconfigured.
  static Future<HomeLocationSettings> load() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString(kKey);
    if (stored == null) return const HomeLocationSettings();
    try {
      final decoded = jsonDecode(stored);
      if (decoded is! Map<String, dynamic>) return const HomeLocationSettings();
      final bssids = decoded['bssids'];
      return HomeLocationSettings(
        ssid: decoded['ssid'] as String?,
        bssids: bssids is List
            ? bssids.whereType<String>().map((b) => b.toLowerCase()).toList()
            : const <String>[],
        lat: (decoded['lat'] as num?)?.toDouble(),
        lon: (decoded['lon'] as num?)?.toDouble(),
        radiusMeters:
            (decoded['radiusMeters'] as num?)?.toDouble() ??
            defaultRadiusMeters,
      );
    } on FormatException {
      return const HomeLocationSettings();
    }
  }

  /// Records this place as home, merging [bssid] into any already captured.
  ///
  /// Merging rather than replacing is what lets a second press on the other
  /// band add to the set instead of overwriting it.
  static Future<HomeLocationSettings> capture({
    String? ssid,
    String? bssid,
    double? lat,
    double? lon,
  }) async {
    final current = await load();
    final merged = <String>{
      ...current.bssids,
      if (bssid != null) bssid.toLowerCase(),
    }.toList();
    final next = HomeLocationSettings(
      ssid: ssid ?? current.ssid,
      bssids: merged,
      lat: lat ?? current.lat,
      lon: lon ?? current.lon,
      radiusMeters: current.radiusMeters,
    );
    await _save(next);
    return next;
  }

  /// Forgets the stored home, returning the app to the strict sequence.
  static Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(kKey);
  }

  static Future<void> _save(HomeLocationSettings value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      kKey,
      jsonEncode(<String, Object?>{
        'ssid': value.ssid,
        'bssids': value.bssids,
        'lat': value.lat,
        'lon': value.lon,
        'radiusMeters': value.radiusMeters,
      }),
    );
  }
}
