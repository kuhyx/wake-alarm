import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_keep.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';

import 'fake_day_pool_store.dart';

/// The Python -> Dart half of `scripts/sick_days_interop/check.sh`.
///
/// Reads the pool `verify.py write` made with `sickdays` (Python) from
/// `SICK_DAYS_INTEROP_IN` -- 0.2.0 keep sets plus a 0.1.0 record with no
/// keep, a stale keep and a malformed one -- and writes the Dart verdicts to
/// `SICK_DAYS_INTEROP_READING` for `verify.py read` to compare with
/// Python's. Under a plain `flutter test` both are unset and this does
/// nothing.
void main() {
  test('writes the Dart reading of a Python pool when asked', () async {
    final input = Platform.environment['SICK_DAYS_INTEROP_IN'];
    final output = Platform.environment['SICK_DAYS_INTEROP_READING'];
    if (input == null || output == null) return;
    final pool = await SickDayPool.open(
      persistence: MemPersistence(),
      deviceId: 'dart-interop',
    );
    await pool.replaceAll(logFromJson(File(input).readAsStringSync()));
    final days = [
      for (final d in [20, 22, 23, 24, 25, 26]) DateTime(2026, 10, d),
    ];
    final reading = <String, Object?>{
      for (final day in days)
        FreeDayPool.toIso(day): {
          'sick': pool.isSick(day),
          'kept': pool.keptLockers(day).toList()..sort(),
          'stands_down': {
            for (final locker in SickLocker.all)
              locker: pool.standsDown(locker, day),
          },
        },
      'sick_days': pool.sickIsoDates(),
    };
    File(output).writeAsStringSync(jsonEncode(reading));
  });
}
