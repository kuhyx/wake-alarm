import 'package:flutter/material.dart';
import 'package:sync_settings_ui/sync_settings_ui.dart';

import 'package:wake_alarm_sync/screens/github_mirror_screen.dart';
import 'package:wake_alarm_sync/screens/room_proof_screen.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/google_sign_in_backend.dart';

/// Settings screen: links to the two sync surfaces.
///
/// "Sync settings" is the shared `sync_settings_ui` package (Firebase,
/// identical in shape to every other kuhy app's Sync settings screen).
/// "Advanced sync (GitHub)" stays app-local ([GitHubMirrorScreen]), and
/// "Room proof" registers the NFC tag / QR code ([RoomProofScreen]) — without
/// a registered tag, NFC can never satisfy the dismiss room proof.
class SettingsScreen extends StatelessWidget {
  /// Creates a [SettingsScreen].
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Sync settings'),
            subtitle: const Text('Firebase sync'),
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
            contentPadding: EdgeInsets.zero,
            title: const Text('Room proof'),
            subtitle: const Text('NFC tag and QR code for the other room'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push<void>(
              MaterialPageRoute(builder: (_) => const RoomProofScreen()),
            ),
          ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Advanced sync (GitHub)'),
            subtitle: const Text('Cutover mirror — not recommended'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push<void>(
              MaterialPageRoute(builder: (_) => const GitHubMirrorScreen()),
            ),
          ),
        ],
      ),
    );
  }
}
