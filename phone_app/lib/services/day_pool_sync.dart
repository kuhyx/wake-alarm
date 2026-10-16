import 'dart:developer' as developer;

import 'package:crdt_sync/crdt_sync.dart';

/// One pull/merge/push tick for a day pool (free days, sick days), then a
/// refresh of that pool's native ring-path cache.
///
/// Shared by `FreeDaySync` and `SickDaySync`, which differ only in where
/// the log lives and which cache it feeds. Firebase only: neither namespace
/// ever had a GitHub mirror.
///
/// Returns a status line for the screen. Never throws: this also runs
/// unattended (app launch, the pre-alarm sync), where a dead network must
/// degrade to a message. [publish] runs whatever happened, so a day marked
/// offline still reaches the ring path.
Future<String> syncDayPoolLog({
  required Future<RemoteStore?> Function() openClient,
  required String deviceId,
  required String pathPrefix,
  required String filename,
  required String commitMessage,
  required Log Function() snapshot,
  required Future<void> Function(Log merged) replaceAll,
  required Future<void> Function() publish,
  required String logName,
}) async {
  final RemoteStore? client;
  try {
    client = await openClient();
  } on Object catch (error, stackTrace) {
    developer.log(
      'could not open Firebase',
      name: logName,
      error: error,
      stackTrace: stackTrace,
    );
    await publish();
    return 'Error: $error';
  }
  if (client == null) {
    await publish();
    return 'Not synced — connect Firebase in Settings.';
  }
  try {
    final merged = await syncLog(
      client: client,
      deviceId: deviceId,
      pathPrefix: pathPrefix,
      filename: filename,
      localLog: snapshot(),
      encode: logToJson,
      decode: logFromJson,
      commitMessage: commitMessage,
    );
    await replaceAll(merged);
    return 'Synced ✓';
  } on Exception catch (e) {
    return 'Error: $e';
  } finally {
    await publish();
  }
}

/// Runs [write] (a native-cache write) and swallows a missing platform:
/// widget tests and probe entry points have no channel, the Dart pool is
/// still correct, and the cache is rewritten on the next sync anyway.
Future<void> publishQuietly(
  Future<void> Function() write, {
  required String logName,
}) async {
  try {
    await write();
  } on Object catch (error) {
    developer.log('native cache not written: $error', name: logName);
  }
}
