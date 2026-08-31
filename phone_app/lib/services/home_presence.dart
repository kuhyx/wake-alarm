import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/home_location_settings.dart';

/// Where the phone is, as far as the dismiss sequence is concerned.
enum PresenceState {
  /// At the registered home: the full strict sequence applies.
  home,

  /// Not at the registered home, or presence could not be read at all.
  away,
}

/// A presence verdict and the reason for it.
///
/// [detail] is shown to the user rather than logged away: an unreadable
/// signal resolves to [PresenceState.away], which silently drops the two tag
/// stages, so the cause has to be visible somewhere.
class PresenceVerdict {
  /// Creates a verdict.
  const PresenceVerdict(this.state, this.detail);

  /// Whether the phone counts as being at home.
  final PresenceState state;

  /// Why, in words fit for the home screen.
  final String detail;

  /// Whether the two NFC tag stages should be skipped.
  bool get skipsTags => state == PresenceState.away;
}

/// Decides whether the phone is at its registered home.
///
/// Wi-Fi first, GPS only as a fallback: at home the network name is instant
/// and works indoors, while a fix at 06:00 with the screen off may take 30
/// seconds or never arrive.
///
/// **Unreadable means away.** A denied permission, a disabled location
/// service, Wi-Fi off with no fix — all of it resolves to
/// [PresenceState.away] rather than guessing. The one exception is an
/// unconfigured home, which stays [PresenceState.home]: see
/// [HomeLocationSettings].
class HomePresence {
  /// Creates a resolver; [scheduler] is injectable so tests need no platform.
  HomePresence({AlarmScheduler? scheduler})
    : _scheduler = scheduler ?? AlarmScheduler();

  final AlarmScheduler _scheduler;

  /// Resolves presence. Never throws — any failure is a verdict, not an error.
  Future<PresenceVerdict> resolve() async {
    final settings = await HomeLocationSettings.load();
    if (!settings.isConfigured) {
      return const PresenceVerdict(
        PresenceState.home,
        'no home registered — full sequence',
      );
    }
    Map<String, Object?>? reading;
    try {
      reading = await _scheduler.readPresence(
        homeLat: settings.lat,
        homeLon: settings.lon,
      );
    } on Object {
      // A missing platform, a channel error, a thrown SecurityException: all
      // of it is "cannot tell", which is away.
      reading = null;
    }
    return decide(settings, reading);
  }

  /// The whole comparison, pure: no channel, no preferences, no clock.
  static PresenceVerdict decide(
    HomeLocationSettings settings,
    Map<String, Object?>? reading,
  ) {
    if (reading == null) {
      return const PresenceVerdict(PresenceState.away, 'presence unreadable');
    }
    final ssid = reading['ssid'] as String?;
    final bssid = reading['bssid'] as String?;
    if (settings.matchesWifi(ssid: ssid, bssid: bssid)) {
      return PresenceVerdict(
        PresenceState.home,
        'home Wi-Fi (${ssid ?? bssid})',
      );
    }
    final distance = (reading['distanceMeters'] as num?)?.toDouble();
    if (distance != null && settings.hasCoordinate) {
      // The accuracy circle counts in the user's favour. A coarse network fix
      // indoors is routinely 100m+, and being lenient here can only ever err
      // towards the strict sequence at home — never towards a hotel.
      final accuracy = (reading['accuracy'] as num?)?.toDouble() ?? 0;
      if (distance <= settings.radiusMeters + accuracy) {
        return PresenceVerdict(
          PresenceState.home,
          'within ${distance.round()} m of home',
        );
      }
      return PresenceVerdict(
        PresenceState.away,
        '${_readableDistance(distance)} from home',
      );
    }
    if (ssid != null || bssid != null) {
      return PresenceVerdict(
        PresenceState.away,
        'on ${ssid ?? bssid}, not the home Wi-Fi',
      );
    }
    return PresenceVerdict(
      PresenceState.away,
      _reasonText(reading['reason'] as String?),
    );
  }

  static String _readableDistance(double metres) => metres >= 1000
      ? '${(metres / 1000).round()} km'
      : '${metres.round()} m';

  static String _reasonText(String? reason) => switch (reason) {
    'no-permission' => 'location permission denied',
    'location-disabled' => 'location services are off',
    'no-fix' => 'no location fix',
    _ => 'presence unreadable',
  };
}
