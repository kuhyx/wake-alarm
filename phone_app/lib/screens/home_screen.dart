import 'dart:async';

import 'package:flutter/material.dart';

import 'package:wake_alarm_sync/screens/settings_screen.dart';
import 'package:wake_alarm_sync/services/alarm_policy.dart';
import 'package:wake_alarm_sync/services/alarm_publisher.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/sync_settings.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// Main screen: displays the current alarm time and syncs it to the PC via
/// the shared crdt_sync transport.
class HomeScreen extends StatefulWidget {
  /// Creates a [HomeScreen].
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _hour = AlarmPolicy.baselineHour;
  int _minute = AlarmPolicy.baselineMinute;

  /// True while a one-shot earlier start is in force for the next alarm.
  bool _isOverridden = false;
  bool _busy = false;
  String _status = '';
  bool _configured = false;
  AlarmSyncService? _service;

  /// Platform bridge that arms the app's own alarm (item 1).
  final AlarmPublisher _publisher = AlarmPublisher();

  /// Platform bridge used to arm the fixed schedule.
  final AlarmScheduler _scheduler = AlarmScheduler();

  @override
  void initState() {
    super.initState();
    unawaited(_applyPolicy());
    unawaited(_loadSyncState());
    // Publishing to the PC is automatic too: it used to require the same tap
    // that armed the alarm, so a forgotten tap left the PC on its fallback.
    unawaited(_syncToPc());
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
    } on Exception catch (_) {
      // Storage/plugins unavailable (e.g. under a widget test, or a keystore
      // hiccup): keep the on-screen defaults rather than crashing.
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
      helpText: 'Earlier than $current only',
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
    setState(() => _status = 'Armed for ${_fmt(_hour, _minute)} tomorrow.');
  }

  /// Re-reads the policy and arms the alarm to match it.
  Future<void> _applyPolicy() async {
    final policy = await AlarmPolicy.load();
    await _scheduler.armSchedule(policy.hour, policy.minute);
    if (!mounted) return;
    setState(() {
      _hour = policy.hour;
      _minute = policy.minute;
      _isOverridden = policy.isOverridden;
    });
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
    });
  }

  /// The baseline time, shown when a one-shot override is active.
  String get _baseline =>
      _fmt(AlarmPolicy.baselineHour, AlarmPolicy.baselineMinute);
  String _fmt(int h, int m) =>
      '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Wake Alarm Sync'),
        actions: [
          IconButton(
            icon: Icon(
              Icons.settings,
              // Dimmed relative to the adjacent title text (rule 28).
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
            onPressed: () async {
              await Navigator.push<void>(
                context,
                MaterialPageRoute<void>(builder: (_) => const SettingsScreen()),
              );
              await _loadSyncState();
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
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  'Alarm is armed for',
                  style: TextStyle(fontSize: 16),
                ),
                const SizedBox(height: 16),
                Text(
                  _fmt(_hour, _minute),
                  style: Theme.of(context).textTheme.displayLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  _isOverridden
                      ? 'One-shot early start — back to $_baseline '
                            'after it rings'
                      : 'Every day. It cannot be turned off.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 13),
                ),
                const SizedBox(height: 32),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: _busy ? null : _pickEarlier,
                    icon: const Icon(Icons.arrow_upward),
                    label: const Text('Wake me earlier tomorrow'),
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                if (_status.isNotEmpty)
                  Text(
                    _status,
                    textAlign: TextAlign.center,
                    // Bounded: _status can be a raw `'Error: $e'`, i.e. an
                    // arbitrarily long exception toString(). Unbounded, that
                    // alone added 100-150px and pushed this column past the
                    // viewport even in portrait. The scroll view above makes
                    // the overflow recoverable; this keeps it from happening.
                    maxLines: 4,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: _status.contains('Error')
                          ? Theme.of(context).colorScheme.error
                          : Theme.of(
                              context,
                            ).extension<AppStatusColors>()!.success,
                    ),
                  ),
                if (!_configured) ...[
                  const SizedBox(height: 16),
                  Text(
                    'Open Settings (gear icon) to connect Firebase.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Theme.of(
                        context,
                      ).extension<AppStatusColors>()!.warning,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
