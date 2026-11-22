// phone-slot: not-shared-storage (path is per-package: Android/data/<package>/files)
import 'dart:io';

import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// Moves an adb-written `files/passphrase` into the keystore, then deletes it.
///
/// The emulator syncs to the PC's RTDB emulator (`sync_emulator.dart`), and
/// every push is end-to-end encrypted: with no passphrase in the keystore it
/// throws `SyncLockedException` and nothing is published. The live checks
/// give the AVD a dummy test passphrase this way, never the real one, and
/// the file does not outlive the first launch. Probe-only.
Future<void> plantProbePassphrase() async {
  final dir = await getExternalStorageDirectory();
  if (dir == null) return;
  final file = File(p.join(dir.path, 'passphrase'));
  if (!file.existsSync()) return;
  await saveE2ePassphrase((await file.readAsString()).trim());
  await file.delete();
}
