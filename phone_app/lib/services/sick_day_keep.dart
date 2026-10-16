import 'dart:developer' as developer;

import 'package:crdt_sync/crdt_sync.dart';

/// The per-day keep set (sickdays 0.2.0): which lockers stay active on a
/// sick day. A Dart port of `sickdays/_keep.py`; the contract is the
/// README's "keep (0.2.0)" section.
///
/// `keep` is one more last-writer-wins field on the day's record, holding a
/// **sorted, de-duplicated** list of locker ids. Sorting is wire format, not
/// tidiness: the RTDB rev is a SHA-256 of the exact serialised string.
///
/// Reading is where the safety lives ([readKeep]): a missing `keep` (every
/// 0.1.0 record) or one stamped older than `state` keeps nothing; a value
/// that is not a list of strings keeps *everything* (the locks apply); an
/// unknown id inside a valid list is ignored, for forward compatibility.
abstract final class SickLocker {
  /// screen-locker's workout lock.
  static const workout = 'workout';

  /// leetcode-guard.
  static const leetcode = 'leetcode';

  /// The book locker.
  static const book = 'book';

  /// diet_guard.
  static const diet = 'diet';

  /// This app: the phone ring, the PC fallback ring, the RTC self-wake, the
  /// missed-alarm penalty / stick and the morning routine.
  static const alarm = 'alarm';

  /// Every known id, in `sickdays.LOCKERS` order.
  static const all = <String>[workout, leetcode, book, diet, alarm];

  /// Returns [locker] if it is a known id; throws [ArgumentError] otherwise
  /// (a programmer error, never a data problem).
  static String validate(String locker) {
    if (!all.contains(locker)) {
      throw ArgumentError.value(
        locker,
        'locker',
        'unknown locker; expected one of ${all.join(', ')}',
      );
    }
    return locker;
  }
}

/// The record field holding the keep set.
const keepField = 'keep';

/// The on-the-wire value of [keep]: validated, de-duplicated and sorted, so
/// two devices holding the same set write the same bytes.
List<String> keepWire(Iterable<String> keep) =>
    keep.map(SickLocker.validate).toSet().toList()..sort();

/// Which known lockers [record]'s day keeps active.
///
/// Only meaningful while the day is sick; callers check that first. The
/// rules run in the README's order: missing -> keep nothing; older than
/// `state` -> stale, keep nothing (a stale malformed value is just stale);
/// not a list of strings -> keep every locker, logged; else the list minus
/// ids this version does not know.
Set<String> readKeep(Record record) {
  final field = record.fields[keepField];
  if (field == null) return <String>{};
  final (value, hlc) = field;
  final state = record.fields['state'];
  if (state != null && hlc < state.$2) return <String>{};
  if (value is! List || value.any((v) => v is! String)) {
    developer.log(
      'sick day ${record.id} has a malformed keep field $value -- every '
      'locker applies',
      name: 'SickDayPool',
      level: 900,
    );
    return SickLocker.all.toSet();
  }
  return value.cast<String>().where(SickLocker.all.contains).toSet();
}
