import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';

/// Half of the cross-language gate (`scripts/free_days_interop/check.sh`).
///
/// Writes a pool through the Dart rules to `FREE_DAYS_INTEROP_OUT`, then the
/// script replays the same edits through the Python package and compares.
/// Under a plain `flutter test` the variable is unset and this does nothing:
/// the point is the comparison, and only the script can make it.
class _FilePersistence implements LogPersistence {
  _FilePersistence(this.file);

  final File file;

  @override
  Future<String?> read() async =>
      file.existsSync() ? file.readAsStringSync() : null;

  @override
  Future<void> write(String text) async => file.writeAsStringSync(text);
}

void main() {
  test('writes the interop fixture when asked', () async {
    final out = Platform.environment['FREE_DAYS_INTEROP_OUT'];
    if (out == null) return;
    final pool = await FreeDayPool.open(
      persistence: _FilePersistence(File(out)),
      deviceId: 'dart-interop',
    );
    final now = DateTime(2026, 9, 11);
    // One of each policy branch: future, today (consumed on the spot),
    // future then refunded, and released only after it had arrived.
    await pool.mark(DateTime(2026, 9, 12), reason: 'from dart', now: now);
    await pool.mark(now, now: now);
    await pool.mark(DateTime(2026, 9, 13), now: now);
    await pool.release(DateTime(2026, 9, 13), now: now);
    await pool.mark(DateTime(2026, 9, 14), now: now);
    await pool.release(DateTime(2026, 9, 14), now: DateTime(2026, 9, 14));
  });
}
