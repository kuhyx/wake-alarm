import 'dart:async';

import 'package:flutter/material.dart';

import 'package:wake_alarm_sync/screens/settings_screen.dart';
import 'package:wake_alarm_sync/services/alarm_arming.dart';
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
  int _hour = 7;
  int _minute = 0;
  bool _busy = false;
  String _status = '';
  bool _configured = false;
  AlarmSyncService? _service;

  /// Platform bridge that arms the app's own alarm (item 1).
  final AlarmArming _arming = AlarmArming(AlarmScheduler());

  @override
  void initState() {
    super.initState();
    unawaited(_loadSavedTime());
  }

  Future<void> _loadSavedTime() async {
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

    final alarm = service.currentAlarm;
    if (alarm != null && mounted) {
      setState(() {
        _hour = alarm.hour;
        _minute = alarm.minute;
        _status = 'Loaded saved alarm';
      });
    }
  }

  Future<void> _pickTime() async {
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: _hour, minute: _minute),
    );
    if (picked != null) {
      setState(() {
        _hour = picked.hour;
        _minute = picked.minute;
        _status = '';
      });
    }
  }

  Future<void> _syncAndSet() async {
    final settings = await SyncSettings.load();
    final service = _service;
    // syncBackend() falls back to GitHub alone, or pushes to Firebase alone
    // via the mirror, so either credential is enough to proceed.
    final hasFirebase = await loadAccount() != null;
    if ((!settings.isConfigured && !hasFirebase) || service == null) {
      setState(() => _status = 'Connect a sync backend in Settings first.');
      return;
    }

    setState(() {
      _busy = true;
      _status = 'Syncing to PC…';
    });
    try {
      await service.setLocal(_hour, _minute);
      await service.push(settings.token);
      setState(() => _status = 'Synced ✓ — arming alarm…');
      final problem = await _arming.arm(_hour, _minute);
      if (problem != null) {
        setState(() => _status = problem);
        return;
      }
      await _arming.registerWithClockApp(_hour, _minute);
      final at = _fmt(_hour, _minute);
      setState(() => _status = 'Done! Alarm armed for $at.');
    } on Exception catch (e) {
      setState(() => _status = 'Error: $e');
    } finally {
      setState(() => _busy = false);
    }
  }

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
              await _loadSavedTime();
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
                const Text('Alarm time', style: TextStyle(fontSize: 16)),
                const SizedBox(height: 16),
                GestureDetector(
                  onTap: _pickTime,
                  child: Text(
                    _fmt(_hour, _minute),
                    style: Theme.of(context).textTheme.displayLarge?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                TextButton(
                  onPressed: _pickTime,
                  child: const Text('Tap to change'),
                ),
                const SizedBox(height: 32),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _busy ? null : _syncAndSet,
                    icon: _busy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.alarm_add),
                    label: const Text('Set Alarm & Sync to PC'),
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      textStyle: const TextStyle(fontSize: 18),
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
