import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/home_location_settings.dart';

/// Registers the Wi-Fi and coordinate that mean "home".
///
/// Capture is a deliberate act, pressed once while at home. Until it is
/// pressed nothing changes: an unregistered home keeps the full strict
/// dismiss sequence everywhere.
///
/// Pressing capture again on the other Wi-Fi band **adds** that access point
/// rather than replacing it — a dual-band router answers to a different
/// address per band and the phone roams between them overnight.
class HomeLocationScreen extends StatefulWidget {
  /// Creates the screen; [scheduler] is injectable so tests need no platform.
  const HomeLocationScreen({super.key, this.scheduler});

  /// Platform bridge; defaults to the real MethodChannel.
  final AlarmScheduler? scheduler;

  @override
  State<HomeLocationScreen> createState() => _HomeLocationScreenState();
}

class _HomeLocationScreenState extends State<HomeLocationScreen> {
  late final AlarmScheduler _scheduler = widget.scheduler ?? AlarmScheduler();

  HomeLocationSettings _home = const HomeLocationSettings();
  String _status = '';
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    unawaited(_reload());
  }

  Future<void> _reload() async {
    final home = await HomeLocationSettings.load();
    if (!mounted) return;
    setState(() => _home = home);
  }

  Future<void> _capture() async {
    setState(() {
      _busy = true;
      _status = 'Reading Wi-Fi and location…';
    });
    Map<String, Object?>? reading;
    try {
      reading = await _scheduler.readPresence(withFix: true);
    } on Object {
      reading = null;
    }
    if (!mounted) return;
    final observed = reading;
    if (observed == null) {
      setState(() {
        _busy = false;
        _status = 'Could not read presence.';
      });
      return;
    }
    final ssid = observed['ssid'] as String?;
    final bssid = observed['bssid'] as String?;
    final lat = (observed['lat'] as num?)?.toDouble();
    final lon = (observed['lon'] as num?)?.toDouble();
    if (ssid == null && bssid == null && lat == null) {
      setState(() {
        _busy = false;
        // Naming the reason matters: a redacted BSSID and a denied permission
        // both look like "nothing here" but need different fixes.
        _status = _reasonText(observed['reason'] as String?);
      });
      return;
    }
    final home = await HomeLocationSettings.capture(
      ssid: ssid,
      bssid: bssid,
      lat: lat,
      lon: lon,
    );
    if (!mounted) return;
    setState(() {
      _home = home;
      _busy = false;
      // Name what actually landed. A capture indoors often gets the Wi-Fi and
      // no fix, and a bare "Captured." next to "Coordinate: not captured"
      // reads as a bug rather than as the GPS fallback being unset.
      _status = home.hasCoordinate
          ? 'Captured Wi-Fi and coordinate.'
          : 'Captured Wi-Fi. No location fix yet — the GPS fallback is unset.';
    });
  }

  Future<void> _clear() async {
    await HomeLocationSettings.clear();
    if (!mounted) return;
    setState(() {
      _home = const HomeLocationSettings();
      _status = 'Cleared — the full sequence now applies everywhere.';
    });
  }

  static String _reasonText(String? reason) => switch (reason) {
    'no-permission' => 'Grant location permission, then try again.',
    'location-disabled' => 'Turn location services on, then try again.',
    'no-fix' => 'No Wi-Fi and no location fix — try again by a window.',
    _ => 'Nothing readable here.',
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Home location')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: <Widget>[
          Text(
            'Away from home the two NFC tags are unreachable, so they are '
            'skipped and the alarm asks the usual questions instead. The '
            'walk is always required.',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: 20),
          Text('Home Wi-Fi', style: theme.textTheme.titleMedium),
          Text(_home.ssid ?? 'not captured'),
          const SizedBox(height: 12),
          Text('Access points', style: theme.textTheme.titleMedium),
          Text(_home.bssids.isEmpty ? 'none' : _home.bssids.join('\n')),
          const SizedBox(height: 12),
          Text('Coordinate', style: theme.textTheme.titleMedium),
          Text(
            _home.hasCoordinate
                ? '${_home.lat!.toStringAsFixed(5)}, '
                      '${_home.lon!.toStringAsFixed(5)} '
                      '(±${_home.radiusMeters.round()} m)'
                : 'not captured',
          ),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _busy ? null : _capture,
            child: const Text('Capture this place as home'),
          ),
          const SizedBox(height: 8),
          Text(
            'Press once on each Wi-Fi band (2.4 GHz and 5 GHz) so a band '
            'switch overnight is not mistaken for travelling.',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: 16),
          TextButton(
            onPressed: _home.isConfigured ? _clear : null,
            child: const Text('Forget home'),
          ),
          const SizedBox(height: 16),
          Text(_status, style: theme.textTheme.bodyMedium),
        ],
      ),
    );
  }
}
