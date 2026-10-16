import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';

/// Half of the cross-language check (`scripts/sick_days_interop/check.sh`).
///
/// Writes a pool through the Dart rules to `SICK_DAYS_INTEROP_OUT`; the
/// script reads it back with `sickdays` (Python) and replays the same edits
/// there. Under a plain `flutter test` the variable is unset and this does
/// nothing.
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
    final out = Platform.environment['SICK_DAYS_INTEROP_OUT'];
    if (out == null) return;
    final pool = await SickDayPool.open(
      persistence: _FilePersistence(File(out)),
      deviceId: 'dart-interop',
    );
    final now = DateTime(2026, 10, 16);
    bool never(DateTime _) => false;
    // Today sick; a future day sick; a future day marked then cleared;
    // 2026-10-23 untouched.
    await pool.add(now, isFree: never, now: now);
    await pool.add(DateTime(2026, 10, 20), isFree: never, now: now);
    await pool.add(DateTime(2026, 10, 21), isFree: never, now: now);
    await pool.remove(DateTime(2026, 10, 21), now: now);
  });
}
