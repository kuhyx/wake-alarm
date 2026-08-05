import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/github_device_auth.dart';
import 'package:wake_alarm_sync/services/sync_settings.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// Settings screen for the backends the alarm syncs through.
///
/// Firebase is the primary path: sign in once with the shared sync account,
/// whose password is kept in the OS keystore. GitHub is only the cutover
/// mirror, so its device-flow connection sits under "Advanced" rather than
/// competing with Firebase as a visible choice.
class SettingsScreen extends StatefulWidget {
  /// Creates a [SettingsScreen].
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  SyncSettings _settings = const SyncSettings(token: '');
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _firebaseConnected = false;
  bool _busy = false;
  String _status = '';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final s = await SyncSettings.load();
    // Reflect a previously-stored account, so a returning user sees the real
    // state instead of an empty form that looks unconfigured.
    final account = await loadAccount();
    if (!mounted) return;
    if (account != null) _emailController.text = account.email;
    setState(() {
      _settings = s;
      _firebaseConnected = account != null;
    });
  }

  /// Stores the typed account and signs in immediately, so a typo surfaces
  /// here rather than as a silent background failure at push time.
  Future<void> _connectFirebase() async {
    final email = _emailController.text.trim();
    final password = _passwordController.text;
    if (email.isEmpty || password.isEmpty) {
      setState(() => _status = 'Enter the sync account email and password.');
      return;
    }
    setState(() {
      _busy = true;
      _status = 'Signing in…';
    });
    await saveAccount(FirebaseAccount(email: email, password: password));
    final client = await openFirebase();
    if (!mounted) return;
    if (client == null) {
      await clearAccount();
      setState(() {
        _busy = false;
        _firebaseConnected = false;
        _status = 'Error: Firebase rejected that account.';
      });
      return;
    }
    _passwordController.clear();
    setState(() {
      _busy = false;
      _firebaseConnected = true;
      _status = 'Connected to Firebase.';
    });
  }

  Future<void> _disconnectFirebase() async {
    await clearAccount();
    if (!mounted) return;
    _emailController.clear();
    _passwordController.clear();
    setState(() {
      _firebaseConnected = false;
      _status = 'Firebase disconnected.';
    });
  }

  Future<void> _connectGitHub() async {
    final auth = GitHubDeviceAuth(clientId: SyncSettings.defaultClientId);
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
      // Scrollable: this screen carries a five-line explanatory paragraph and
      // an unbounded `'Error: \$e'`, inside a Column that could not scroll.
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _StatusCard(connected: _firebaseConnected),
              const SizedBox(height: 16),
              Text(
                'Firebase sync',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              Text(
                _firebaseConnected
                    ? 'Connected. The alarm goes to Firebase first, and still '
                          'mirrors to GitHub until every device has moved.'
                    : 'Not connected — syncing over GitHub only. Enter the '
                          'shared sync account to move this device over. The '
                          'password is kept in the device keystore, never in '
                          'the app or the repo.',
                style: TextStyle(
                  fontSize: 16,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 12),
              // Once connected the account is shown as read-only text: an
              // editable email box beside an empty password box reads as
              // "you still have to enter this", making a connected device
              // look unconfigured.
              if (_firebaseConnected)
                Row(
                  children: [
                    const Icon(Icons.cloud_done, size: 20),
                    const SizedBox(width: 8),
                    Expanded(child: Text(_emailController.text)),
                    TextButton(
                      onPressed: _busy ? null : _disconnectFirebase,
                      child: const Text('Disconnect'),
                    ),
                  ],
                )
              else ...[
                TextField(
                  controller: _emailController,
                  keyboardType: TextInputType.emailAddress,
                  autocorrect: false,
                  decoration: const InputDecoration(
                    labelText: 'Sync account email',
                  ),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: _passwordController,
                  obscureText: true,
                  autocorrect: false,
                  decoration: const InputDecoration(
                    labelText: 'Sync account password',
                  ),
                ),
                const SizedBox(height: 12),
                FilledButton.icon(
                  onPressed: _busy ? null : _connectFirebase,
                  icon: _busy
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.cloud_done),
                  label: const Text('Connect Firebase'),
                ),
              ],
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
              // GitHub is the cutover mirror, not a choice: everything about
              // it lives here so the primary path stays a single decision.
              ExpansionTile(
                title: const Text('Advanced (GitHub mirror)'),
                tilePadding: EdgeInsets.zero,
                childrenPadding: const EdgeInsets.only(bottom: 8),
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
                    // Was 12px/Colors.grey — below the 16px reading floor
                    // (rule 20) and off-palette (rule 4); this is real setup
                    // instructions, not decorative chrome.
                    style: TextStyle(
                      fontSize: 16,
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ],
          ),
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
              color: (connected ? success : colorScheme.error).withValues(
                alpha: 0.8,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                connected ? 'Connected to Firebase' : 'Not connected',
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
    await Clipboard.setData(ClipboardData(text: widget.device.userCode));
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
                Expanded(child: Text('Waiting for authorization…')),
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
