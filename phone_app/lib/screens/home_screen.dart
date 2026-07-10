import 'dart:async';

import 'package:android_intent_plus/android_intent.dart';
import 'package:flutter/material.dart';

import 'package:wake_alarm_sync/screens/settings_screen.dart';
import 'package:wake_alarm_sync/services/gist_service.dart';
import 'package:wake_alarm_sync/services/sync_settings.dart';

/// Main screen: displays the current alarm time and syncs it to the Gist.
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

  @override
  void initState() {
    super.initState();
    unawaited(_loadSavedTime());
  }

  Future<void> _loadSavedTime() async {
    final settings = await SyncSettings.load();
    if (!mounted) return;
    setState(() => _configured = settings.isConfigured);
    if (!settings.isConfigured) return;

    try {
      final time = await readGistAlarm(
        token: settings.token,
        gistId: settings.gistId,
      );
      if (time != null && mounted) {
        setState(() {
          _hour = time.hour;
          _minute = time.minute;
          _status = 'Loaded from Gist';
        });
      }
    } on Exception catch (_) {
      // Non-fatal: local defaults used.
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

  /// Opens the system Clock app pre-filled via ACTION_SET_ALARM.
  ///
  /// android_intent_plus v5 uses startActivityForResult; the Clock app
  /// never sends a result, so we time out after 3 s rather than hang forever.
  Future<void> _setPhoneAlarm() async {
    final intent = AndroidIntent(
      action: 'android.intent.action.SET_ALARM',
      arguments: {
        'android.intent.extra.alarm.HOUR': _hour,
        'android.intent.extra.alarm.MINUTES': _minute,
        'android.intent.extra.alarm.SKIP_UI': false,
        'android.intent.extra.alarm.MESSAGE': 'Wake Alarm',
      },
    );
    await intent.launch().timeout(
      const Duration(seconds: 3),
      onTimeout: () {},
    );
  }

  Future<void> _syncAndSet() async {
    final settings = await SyncSettings.load();
    if (!settings.isConfigured) {
      setState(
        () => _status = 'Configure GitHub in Settings first.',
      );
      return;
    }

    setState(() {
      _busy = true;
      _status = 'Syncing to Gist…';
    });
    try {
      await writeGistAlarm(
        token: settings.token,
        gistId: settings.gistId,
        hour: _hour,
        minute: _minute,
      );
      setState(
        () => _status = 'Gist updated ✓ — opening Clock app…',
      );
      await _setPhoneAlarm();
      setState(
        () => _status = 'Done! Confirm the alarm in the Clock app.',
      );
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
            icon: const Icon(Icons.settings),
            onPressed: () async {
              await Navigator.push<void>(
                context,
                MaterialPageRoute<void>(
                  builder: (_) => const SettingsScreen(),
                ),
              );
              await _loadSavedTime();
            },
          ),
        ],
      ),
      body: Center(
        child: Padding(
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
                  style: Theme.of(context)
                      .textTheme
                      .displayLarge
                      ?.copyWith(fontWeight: FontWeight.bold),
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
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                          ),
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
                  style: TextStyle(
                    color: _status.contains('Error')
                        ? Colors.redAccent
                        : Colors.greenAccent,
                  ),
                ),
              if (!_configured) ...[
                const SizedBox(height: 16),
                const Text(
                  'Open Settings (gear icon) to connect GitHub.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.orange),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
