import 'dart:async';

import 'package:flutter/material.dart';
import 'package:github_device_auth/github_device_auth.dart';
import 'package:wake_alarm_sync/services/sync_settings.dart';

/// The GitHub mirror screen: cutover-only sync transport, not a peer of
/// Firebase.
///
/// Kept app-local rather than folded into the shared `sync_settings_ui`
/// package since that package carries no GitHub surface at all. Logic moved
/// verbatim from the old combined settings screen.
class GitHubMirrorScreen extends StatefulWidget {
  /// Creates a [GitHubMirrorScreen].
  const GitHubMirrorScreen({super.key});

  @override
  State<GitHubMirrorScreen> createState() => _GitHubMirrorScreenState();
}

class _GitHubMirrorScreenState extends State<GitHubMirrorScreen> {
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
    if (!mounted) return;
    setState(() => _settings = s);
  }

  Future<void> _connectGitHub() async {
    final auth = GitHubDeviceAuth(clientId: SyncSettings.defaultClientId);
    try {
      final device = await auth.requestDeviceCode();
      if (!mounted) return;
      final token = await showDialog<String>(
        context: context,
        barrierDismissible: false,
        builder: (_) => DeviceCodeDialog(device: device, auth: auth),
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
      appBar: AppBar(title: const Text('Advanced sync (GitHub)')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  isConnected
                      ? 'Connected to GitHub.'
                      : 'Not connected to GitHub.',
                  style: TextStyle(
                    fontSize: 16,
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
              const SizedBox(height: 12),
              if (!isConnected)
                ElevatedButton.icon(
                  onPressed: _busy ? null : _connectGitHub,
                  icon: const Icon(Icons.link),
                  label: const Text('Connect GitHub'),
                )
              else
                OutlinedButton.icon(
                  onPressed: _busy ? null : _disconnect,
                  icon: const Icon(Icons.link_off),
                  label: const Text('Disconnect GitHub'),
                ),
              const SizedBox(height: 16),
              Text(
                'PC config — the PC reads Firebase first and falls back '
                'to GitHub. For the GitHub fallback, create:\n'
                '~/.config/wake_alarm/sync.json\n\n'
                '{ "token": "<same token>" }\n\n'
                'The token needs "repo" scope so the PC can read '
                'kuhyx/syncs.',
                style: TextStyle(
                  fontSize: 16,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
              if (_status.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text(
                  _status,
                  style: TextStyle(
                    color: _status.startsWith('Error')
                        ? Theme.of(context).colorScheme.error
                        : null,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
