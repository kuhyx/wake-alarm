import 'dart:async';

import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/home_location_settings.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/dashed_slot.dart';

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

  Widget _valueRow(IconData icon, String semanticLabel, Widget value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(icon, semanticLabel: semanticLabel, size: 24),
          const SizedBox(width: 12),
          Expanded(child: value),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: <Widget>[
          _valueRow(
            Icons.wifi,
            'Home Wi-Fi',
            KeyedSubtree(
              key: const ValueKey<String>('content:home-ssid'),
              child: _home.ssid != null
                  ? Text(_home.ssid!)
                  : const DashedSlot(),
            ),
          ),
          _valueRow(
            Icons.router,
            'Access points',
            KeyedSubtree(
              key: const ValueKey<String>('content:home-bssids'),
              child: _home.bssids.isEmpty
                  ? const DashedSlot()
                  : Text(_home.bssids.join('\n')),
            ),
          ),
          _valueRow(
            Icons.place,
            'Coordinate',
            KeyedSubtree(
              key: const ValueKey<String>('content:home-coord'),
              child: _home.hasCoordinate
                  ? Text(
                      '${_home.lat!.toStringAsFixed(5)}, '
                      '${_home.lon!.toStringAsFixed(5)} '
                      '(±${_home.radiusMeters.round()} m)',
                    )
                  : const DashedSlot(),
            ),
          ),
          const SizedBox(height: 24),
          Row(
            children: <Widget>[
              FilledButton(
                onPressed: _busy ? null : _capture,
                child: const Icon(
                  Icons.my_location,
                  semanticLabel: 'Capture this place as home',
                ),
              ),
              const SizedBox(width: 12),
              Icon(
                Icons.network_wifi_2_bar,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
                semanticLabel: 'Press once on each Wi-Fi band, 2.4 and 5 GHz',
              ),
              const SizedBox(width: 8),
              Icon(
                Icons.network_wifi,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
                semanticLabel: 'Press once on each Wi-Fi band, 2.4 and 5 GHz',
              ),
            ],
          ),
          const SizedBox(height: 16),
          TextButton(
            onPressed: _home.isConfigured ? _clear : null,
            child: const Icon(
              Icons.delete_outline,
              semanticLabel: 'Forget home',
            ),
          ),
          const SizedBox(height: 16),
          StatusCue(semanticLabel: _status),
        ],
      ),
    );
  }
}
