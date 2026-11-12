import 'dart:developer' as developer;

import 'package:material_ui/material_ui.dart';
import 'package:sync_settings_ui/sync_settings_ui.dart';

import 'package:wake_alarm_sync/screens/github_mirror_screen.dart';
import 'package:wake_alarm_sync/screens/home_location_screen.dart';
import 'package:wake_alarm_sync/screens/room_proof_screen.dart';
import 'package:wake_alarm_sync/screens/session_tags_screen.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/data_transfer.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/google_sign_in_backend.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// Settings screen: links to the two sync surfaces.
///
/// "Sync settings" is the shared `sync_settings_ui` package (Firebase,
/// identical in shape to every other kuhy app's Sync settings screen).
/// "Advanced sync (GitHub)" stays app-local ([GitHubMirrorScreen]), and
/// "Room proof" registers the two NFC tags ([RoomProofScreen]) — without
/// a registered tag, NFC can never satisfy the dismiss room proof.
/// "Home location" ([HomeLocationScreen]) registers where the tags are, so
/// the alarm can skip them when it rings somewhere else.
class SettingsScreen extends StatelessWidget {
  /// Creates a [SettingsScreen].
  const SettingsScreen({
    super.key,
    this.alarmService,
    this.onExport,
    this.onImport,
  });

  /// The home screen's live alarm store, reused by export/import.
  final AlarmSyncService? alarmService;

  /// Export action; defaults to [saveExport].
  final Future<void> Function()? onExport;

  /// Import action, false on cancel; defaults to [pickAndImport].
  final Future<bool> Function()? onImport;

  Future<void> _run(
    BuildContext context,
    Future<bool> Function() action,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    final colors = Theme.of(context).colorScheme;
    var ok = false;
    try {
      if (!await action()) return;
      ok = true;
    } on Object catch (e, stack) {
      developer.log(
        'data transfer failed: $e',
        name: 'WakeAlarmSync',
        error: e,
        stackTrace: stack,
      );
    }
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Icon(
            ok ? Icons.check_circle : Icons.error_outline,
            color: ok ? colors.primary : colors.error,
            semanticLabel: ok ? 'Done' : 'Failed',
          ),
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final statusColors = theme.extension<AppStatusColors>();
    return Scaffold(
      appBar: AppBar(
        actions: [
          IconButton(
            key: const Key('settings-export'),
            icon: const Icon(Icons.upload_file, semanticLabel: 'Export data'),
            onPressed: () => _run(context, () async {
              await (onExport ?? () => saveExport(alarm: alarmService))();
              return true;
            }),
          ),
          IconButton(
            key: const Key('settings-import'),
            icon: const Icon(Icons.download, semanticLabel: 'Import data'),
            onPressed: () => _run(
              context,
              onImport ?? () => pickAndImport(alarm: alarmService),
            ),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          ListTile(
            key: const Key('settings-sync'),
            contentPadding: EdgeInsets.zero,
            leading: const Icon(
              Icons.cloud_sync_outlined,
              semanticLabel: 'Sync settings',
            ),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push<void>(
              MaterialPageRoute(
                builder: (_) => SyncSettingsScreen(
                  accountLoader: loadAccount,
                  accountSaver: saveAccount,
                  accountClearer: clearAccount,
                  sessionProbe: isFirebaseConfigured,
                  firebaseFactory: openFirebase,
                  googleFirebaseFactory: openFirebaseWithGoogle,
                  googleAvailable: googleSignInSupported,
                ),
              ),
            ),
          ),
          ListTile(
            key: const Key('settings-room-proof'),
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.nfc, semanticLabel: 'Room proof'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push<void>(
              MaterialPageRoute(builder: (_) => const RoomProofScreen()),
            ),
          ),
          ListTile(
            key: const Key('settings-session-tags'),
            contentPadding: EdgeInsets.zero,
            leading: const Icon(
              Icons.checklist,
              semanticLabel: 'Morning session tags',
            ),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push<void>(
              MaterialPageRoute(builder: (_) => const SessionTagsScreen()),
            ),
          ),
          ListTile(
            key: const Key('settings-home'),
            contentPadding: EdgeInsets.zero,
            leading: const Icon(
              Icons.home_outlined,
              semanticLabel: 'Home location',
            ),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push<void>(
              MaterialPageRoute(builder: (_) => const HomeLocationScreen()),
            ),
          ),
          ListTile(
            key: const Key('settings-github'),
            contentPadding: EdgeInsets.zero,
            leading: Icon(
              Icons.code,
              color: colors.onSurfaceVariant.withValues(alpha: 0.6),
              semanticLabel: 'Advanced sync (GitHub)',
            ),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.warning_amber_rounded,
                  color: statusColors?.warning ?? colors.error,
                  semanticLabel: 'Cutover mirror, not recommended',
                ),
                const Icon(Icons.chevron_right),
              ],
            ),
            onTap: () => Navigator.of(context).push<void>(
              MaterialPageRoute(builder: (_) => const GitHubMirrorScreen()),
            ),
          ),
        ],
      ),
    );
  }
}
