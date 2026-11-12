/// End-to-end encryption of the alarm record this app publishes.
///
/// The record (alarm time, tags, home location, morning sessions, weigh-ins,
/// enforcement fields) is sealed with a key derived from the shared
/// crdt-sync passphrase in the OS keystore, under
/// `wake-alarm-sync/devices-e2e`; Firebase and the GitHub mirror only see
/// the record id and clocks. The PC (`wake_alarm/_sync_transport.py`) and
/// diet_guard (its weigh-in ingest) read the same layout.
///
/// Fail closed: without a usable key nothing is pulled or pushed. The old
/// plaintext prefix is copied over on open and never written or deleted.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync_flutter/crdt_sync_flutter.dart'
    show openEncryptedStoreFromKeystore;
import 'package:flutter/foundation.dart';

/// The plaintext prefix every pre-E2E build wrote; only the copy reads it.
const legacyAlarmPrefix = 'wake-alarm-sync/devices';

/// Where the alarm record now lives, and where its revisions go.
final E2eLayout alarmLayout = E2eLayout.of(legacyAlarmPrefix);

/// Argon2id cost for a header this device creates; only tests lower it.
@visibleForTesting
Argon2Params e2eArgon2Params = Argon2Params.recommended;

/// Whether the last open found no usable key, for the lock button.
final ValueNotifier<bool> alarmSyncLocked = ValueNotifier<bool>(false);

/// Thrown instead of syncing when end-to-end encryption has no usable key.
class SyncLockedException implements Exception {
  /// Creates the exception for [reason].
  const SyncLockedException(this.reason);

  /// Why the store is locked.
  final E2eLockReason reason;

  @override
  String toString() => 'sync locked (${reason.name})';
}

/// The encrypted view of [backend], the outermost store (above the mirror).
///
/// Throws [SyncLockedException] when locked, so no caller can fall through
/// to a plaintext push.
Future<RemoteStore> openAlarmStore(RemoteStore backend) async {
  final state = await openEncryptedStoreFromKeystore(
    store: backend,
    oldPrefix: legacyAlarmPrefix,
    params: e2eArgon2Params,
  );
  alarmSyncLocked.value = state is! E2eReady;
  if (state is E2eReady) return state.store;
  throw SyncLockedException(
    state is E2eLocked ? state.reason : E2eLockReason.badHeader,
  );
}
