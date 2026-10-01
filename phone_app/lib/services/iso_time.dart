/// ISO-8601 with the local UTC offset, the shape the enforcement contract's
/// `at` fields use (`2026-10-01T07:15:03+02:00`).
///
/// `DateTime.toIso8601String()` on a local time has no offset at all, which
/// the PC would read as its own local time -- right by coincidence at home,
/// wrong by hours on any phone that travelled.
library;

/// [when] as `yyyy-MM-ddTHH:mm:ss±hh:mm`, seconds precision.
String isoWithOffset(DateTime when) {
  final local = when.toLocal();
  final offset = local.timeZoneOffset;
  final sign = offset.isNegative ? '-' : '+';
  final minutes = offset.inMinutes.abs();
  return '${_date(local)}T${_two(local.hour)}:${_two(local.minute)}:'
      '${_two(local.second)}$sign${_two(minutes ~/ 60)}:${_two(minutes % 60)}';
}

/// `yyyy-MM-dd` of [day]'s local calendar date.
String isoDate(DateTime day) => _date(day);

String _date(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${_two(d.month)}-${_two(d.day)}';

String _two(int n) => n.toString().padLeft(2, '0');
