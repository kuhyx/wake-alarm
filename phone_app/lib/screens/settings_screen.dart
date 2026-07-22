import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:wake_alarm_sync/services/github_device_auth.dart';
import 'package:wake_alarm_sync/services/sync_settings.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// Settings screen for the GitHub connection used to sync the alarm.
///
/// The "Connect GitHub" button runs the OAuth device flow — the user
/// enters a short code on github.com; no token pasting required.
class SettingsScreen extends StatefulWidget {
  /// Creates a [SettingsScreen].
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  SyncSettings _settings = const SyncSettings(token: '');
  bool _busy = false;
  String _status = '';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    final s = await SyncSettings.load();
    if (mounted) setState(() => _settings = s);
  }

  Future<void> _connectGitHub() async {
    final auth = GitHubDeviceAuth(
      clientId: SyncSettings.defaultClientId,
    );
    try {
      final device = await auth.requestDeviceCode();
      if (!mounted) return;
      final token = await showDialog<String>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _DeviceCodeDialog(device: device, auth: auth),
      );
      if (token == null || token.isEmpty) return;

      setState(() {
        _busy = true;
        _status = 'Connecting…';
      });
      final updated = SyncSettings(token: token);
      await updated.save();
      if (mounted) {
        setState(() {
          _settings = updated;
          _busy = false;
          _status = 'Connected! Alarm will sync to kuhyx/syncs.';
        });
      }
    } on Exception catch (e) {
      if (mounted) {
        setState(() {
          _busy = false;
          _status = 'Error: $e';
        });
      }
    } finally {
      auth.close();
    }
  }

  Future<void> _disconnect() async {
    await SyncSettings.clear();
    if (mounted) {
      setState(() {
        _settings = const SyncSettings(token: '');
        _status = 'Disconnected.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isConnected = _settings.isConfigured;
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _StatusCard(connected: isConnected),
            const SizedBox(height: 16),
            if (!isConnected)
              ElevatedButton.icon(
                onPressed: _busy ? null : _connectGitHub,
                icon: _busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.link),
                label: const Text('Connect GitHub'),
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  textStyle: const TextStyle(fontSize: 16),
                ),
              )
            else
              OutlinedButton.icon(
                onPressed: _busy ? null : _disconnect,
                icon: const Icon(Icons.link_off),
                label: const Text('Disconnect'),
              ),
            const SizedBox(height: 16),
            if (_status.isNotEmpty)
              Text(
                _status,
                style: TextStyle(
                  color: _status.contains('Error')
                      ? Theme.of(context).colorScheme.error
                      : Theme.of(
                          context,
                        ).extension<AppStatusColors>()!.success,
                ),
              ),
            const Divider(height: 32),
            Text(
              'PC config — create this file:\n'
              '~/.config/wake_alarm/sync.json\n\n'
              '{ "token": "<same token>" }\n\n'
              'The token needs "repo" scope so the PC can read '
              'kuhyx/syncs at shutdown.',
              // Was 12px/Colors.grey — below the 16px reading floor (rule
              // 20) and off-palette (rule 4); this is real setup
              // instructions, not decorative chrome.
              style: TextStyle(
                fontSize: 16,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.connected});

  final bool connected;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final success = Theme.of(context).extension<AppStatusColors>()!.success;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(
              connected ? Icons.check_circle : Icons.cancel,
              // Dimmed relative to the adjacent label text (rule 28).
              color: (connected ? success : colorScheme.error)
                  .withValues(alpha: 0.8),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                connected ? 'Connected to GitHub' : 'Not connected',
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Dialog shown while waiting for the user to authorize on GitHub.
class _DeviceCodeDialog extends StatefulWidget {
  const _DeviceCodeDialog({required this.device, required this.auth});

  final DeviceCodeResponse device;
  final GitHubDeviceAuth auth;

  @override
  State<_DeviceCodeDialog> createState() => _DeviceCodeDialogState();
}

class _DeviceCodeDialogState extends State<_DeviceCodeDialog> {
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_poll());
  }

  Future<void> _poll() async {
    try {
      final token = await widget.auth.pollForToken(widget.device);
      if (mounted) Navigator.of(context).pop(token);
    } on Exception catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _openPage() async {
    await Clipboard.setData(
      ClipboardData(text: widget.device.userCode),
    );
    await launchUrl(
      Uri.parse(widget.device.verificationUri),
      mode: LaunchMode.externalApplication,
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Authorize on GitHub'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Enter this code on GitHub:'),
          const SizedBox(height: 8),
          SelectableText(
            widget.device.userCode,
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 16),
          if (_error == null)
            const Row(
              children: [
                SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                SizedBox(width: 12),
                Expanded(
                  child: Text('Waiting for authorization…'),
                ),
              ],
            )
          else
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          onPressed: _openPage,
          icon: const Icon(Icons.open_in_new),
          label: const Text('Open GitHub & copy code'),
        ),
      ],
    );
  }
}
