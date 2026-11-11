import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/material.dart';

import 'package:wake_alarm_sync/screens/free_days_screen.dart';
import 'package:wake_alarm_sync/screens/home_body.dart';
import 'package:wake_alarm_sync/screens/settings_screen.dart';
import 'package:wake_alarm_sync/screens/sick_days_screen.dart';
import 'package:wake_alarm_sync/services/alarm_policy.dart';
import 'package:wake_alarm_sync/services/alarm_publisher.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/day_pool_refresh.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/sync_settings.dart';

/// Main screen: displays the current alarm time and syncs it to the PC via
/// the shared crdt_sync transport.
class HomeScreen extends StatefulWidget {
  /// Creates a [HomeScreen].
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  /// The next alarm: the day's ramp baseline, or a one-shot earlier start.
  AlarmPolicy _policy = AlarmPolicy.resolve(DateTime.now(), null);
  int get _hour => _policy.hour;
  int get _minute => _policy.minute;
  bool _busy = false;
  String _status = '';
  bool _configured = false;
  int _syncEpoch = 0;
  AlarmSyncService? _service;

  /// Platform bridge that arms the app's own alarm (item 1).
  final AlarmPublisher _publisher = AlarmPublisher();

  /// Platform bridge used to arm the fixed schedule.
  final AlarmScheduler _scheduler = AlarmScheduler();

  @override
  void initState() {
    super.initState();
    // STRICTLY SEQUENTIAL. These three used to run concurrently, and the
    // last one reads what the first two write: `publish` takes the service as
    // a *parameter*, so it captured `_service` while it was still null and
    // every startup publish returned "connect a backend" while a backend was
    // connected. `_applyPolicy` has the same shape -- publishing before it
    // resolves would send the baseline instead of an active override.
    unawaited(_bootstrapSync());
  }

  /// Resolves the policy and the sync store, then publishes -- in that order.
  ///
  /// Publishing to the PC is automatic: it used to require the same tap that
  /// armed the alarm, so a forgotten tap left the PC on its fallback.
  Future<void> _bootstrapSync() async {
    await _applyPolicy();
    await _loadSyncState();
    await _syncToPc();
    // Last, and silent: free and sick days marked on the PC reach the
    // native ring path here; an unreadable pool means the alarm rings.
    await refreshDayPools();
  }

  /// Opens the sync store and records whether a backend is connected.
  ///
  /// No longer loads a *time*: the schedule is baked in and owned by
  /// [AlarmPolicy], so a stored value could only disagree with it. This exists
  /// to supply the store for publishing and to drive the "connect a backend"
  /// hint.
  Future<void> _loadSyncState() async {
    final SyncSettings settings;
    final AlarmSyncService service;
    try {
      settings = await SyncSettings.load();
      service = await AlarmSyncService.open();
    } on Exception catch (e, stack) {
      // Storage/plugins unavailable (e.g. under a widget test, or a keystore
      // hiccup): keep the on-screen defaults rather than crashing. Logged
      // rather than swallowed -- silence here is what made a broken store
      // look like an unconfigured backend for weeks.
      developer.log(
        'sync store unavailable: $e',
        name: 'WakeAlarmSync',
        error: e,
        stackTrace: stack,
      );
      return;
    }
    // Either backend counts: a device connected only to Firebase is fully
    // configured, and gating on the GitHub token alone would lock it out of
    // syncing entirely once the mirror is retired.
    final firebaseAccount = await loadAccount();
    if (!mounted) return;
    _service = service;
    setState(
      () => _configured = settings.isConfigured || firebaseAccount != null,
    );
  }

  /// Lets the user move **tomorrow's** alarm earlier, never later.
  ///
  /// This is the only schedule edit the app offers. Earlier-only is what makes
  /// it tamper-proof: every change available costs the user sleep, so there is
  /// no lever a half-asleep user can pull to stay in bed. A later time, a
  /// skipped day and an off switch are simply not expressible.
  Future<void> _pickEarlier() async {
    final current = _fmt(_hour, _minute);
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: _hour, minute: _minute),
      helpText: '',
    );
    if (picked == null) return;
    final accepted = await AlarmPolicy.setEarlier(picked.hour, picked.minute);
    if (!mounted) return;
    if (!accepted) {
      setState(
        () => _status =
            'That is not earlier than $current. The alarm can only be '
            'moved earlier.',
      );
      return;
    }
    await _applyPolicy();
    if (!mounted) return;
    setState(() => _status = 'Armed for ${_fmt(_hour, _minute)}.');
    // The PC has to learn about the new time too. Without this the only
    // publish attempt was the one at startup, so an alarm moved earlier here
    // never reached the PC at all.
    await _syncToPc();
  }

  /// Re-reads the policy and arms the alarm to match it.
  Future<void> _applyPolicy() async {
    final policy = await AlarmPolicy.load();
    await _scheduler.armSchedule(policy.hour, policy.minute);
    if (!mounted) return;
    setState(() => _policy = policy);
  }

  Future<void> _syncToPc() async {
    setState(() {
      _busy = true;
      _status = 'Syncing to PC…';
    });
    final message = await _publisher.publish(
      service: _service,
      hour: _hour,
      minute: _minute,
    );
    if (!mounted) return;
    setState(() {
      _status = message;
      _busy = false;
      _syncEpoch++;
    });
  }

  /// The baseline time, shown when a one-shot override is active.
  String get _baseline => _fmt(_policy.baselineHour, _policy.baselineMinute);
  String _fmt(int h, int m) =>
      '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        actions: [
          IconButton(
            icon: Icon(
              Icons.event_available,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
              semanticLabel: 'Free days',
            ),
            onPressed: () => Navigator.push<void>(
              context,
              MaterialPageRoute<void>(builder: (_) => const FreeDaysScreen()),
            ),
          ),
          IconButton(
            icon: Icon(
              Icons.sick_outlined,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
              semanticLabel: 'Sick days',
            ),
            onPressed: () => Navigator.push<void>(
              context,
              MaterialPageRoute<void>(builder: (_) => const SickDaysScreen()),
            ),
          ),
          IconButton(
            icon: Icon(
              Icons.settings,
              // Dimmed relative to the adjacent title text (rule 28).
              color: Theme.of(context).colorScheme.onSurfaceVariant,
              semanticLabel: 'Settings',
            ),
            onPressed: () async {
              await Navigator.push<void>(
                context,
                MaterialPageRoute<void>(
                  builder: (_) => SettingsScreen(alarmService: _service),
                ),
              );
              // Publish too, not just reload: a tag registered in Settings
              // reaches the backend now, not on the next cold start.
              await _loadSyncState();
              await _syncToPc();
            },
          ),
        ],
      ),
      // SafeArea + scroll. This was a bare Center/Padding/Column, which
      // cannot scroll, so the content simply overflowed with the black-and-
      // yellow stripe pattern painted over the primary control. Two ways that
      // happened: phone landscape leaves only ~360px of body height for ~405px
      // of content, and the status line renders an unbounded raw
      // `'Error: \$e'` with no maxLines, which overflows even in portrait.
      body: HomeBody(
        time: _fmt(_hour, _minute),
        baseline: _baseline,
        isOverridden: _policy.isOverridden,
        busy: _busy,
        status: _status,
        configured: _configured,
        syncEpoch: _syncEpoch,
        onPickEarlier: () => unawaited(_pickEarlier()),
        onEscaped: () => unawaited(_syncToPc()),
      ),
    );
  }
}
