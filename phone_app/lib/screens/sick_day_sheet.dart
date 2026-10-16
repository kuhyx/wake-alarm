import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_keep.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';

/// What each locker is called on screen, in `sickdays.LOCKERS` order.
const sickLockerLabels = <String, String>{
  SickLocker.workout: 'Workout lock',
  SickLocker.leetcode: 'LeetCode',
  SickLocker.book: 'Book',
  SickLocker.diet: 'Diet',
  SickLocker.alarm: 'Wake alarm',
};

/// The kept lockers of a day as one line, in [sickLockerLabels] order.
String keptLabel(Set<String> kept) => [
  for (final MapEntry(:key, :value) in sickLockerLabels.entries)
    if (kept.contains(key)) value,
].join(', ');

/// What the sheet was closed with.
enum SickSheetAction {
  /// Mark a normal day sick, keeping the switched-on lockers.
  mark,

  /// Replace a sick day's kept lockers (a keep-only edit).
  save,

  /// Clear a sick day back to normal.
  clear,
}

/// The sheet's answer: an action and the switches as they stood.
typedef SickSheetResult = ({SickSheetAction action, Set<String> keep});

/// Why [day] cannot be marked sick for the free-day pool, or null.
///
/// An unopenable free-day pool ([free] null) refuses: "could not check"
/// must never count as "not a free day".
String? freeDayRefusal(FreeDayPool? free, DateTime day) {
  if (free == null) {
    return 'Free-day pool unavailable — cannot rule out a free day on '
        '${FreeDayPool.toIso(day)}.';
  }
  if (!free.isFree(day)) return null;
  return '${FreeDayPool.toIso(day)} is a free day — release it in Free '
      'days first.';
}

/// Applies [result] to [day] in [pool]; true when anything was written.
///
/// A Save that changes nothing writes nothing: a fresh tick on an unchanged
/// keep set would only churn the sync. A mark re-checks [free] through the
/// pool (null refuses). Throws what the pool throws.
Future<bool> applySickSheet(
  SickDayPool pool,
  DateTime day,
  SickSheetResult result, {
  required FreeDayPool? free,
  required DateTime now,
}) async {
  switch (result.action) {
    case SickSheetAction.mark:
      final refusal = freeDayRefusal(free, day);
      if (refusal != null) throw SickDayPolicyError(refusal);
      await pool.add(day, isFree: free!.isFree, now: now, keep: result.keep);
    case SickSheetAction.save:
      if (setEquals(result.keep, pool.keptLockers(day))) return false;
      await pool.setKept(day, result.keep, now: now);
    case SickSheetAction.clear:
      await pool.remove(day, now: now);
  }
  return true;
}

/// Opens [SickDaySheet] for [day]; null when dismissed.
Future<SickSheetResult?> showSickDaySheet(
  BuildContext context, {
  required DateTime day,
  required bool isSick,
  required Set<String> kept,
}) => showModalBottomSheet<SickSheetResult>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (_) => SickDaySheet(day: day, isSick: isSick, kept: kept),
);

/// One switch per locker for one day: on = the locker still applies,
/// off = it stands down. A normal day opens with every switch off and a
/// "Mark sick" confirm; a sick day opens with its current switches, "Save"
/// (a keep-only edit) and "Clear sick day".
class SickDaySheet extends StatefulWidget {
  /// Creates the sheet for [day].
  const SickDaySheet({
    required this.day,
    required this.isSick,
    required this.kept,
    super.key,
  });

  /// The date being marked or edited.
  final DateTime day;

  /// Whether [day] is already sick (edit) rather than normal (mark).
  final bool isSick;

  /// The switches to start from.
  final Set<String> kept;

  @override
  State<SickDaySheet> createState() => _SickDaySheetState();
}

class _SickDaySheetState extends State<SickDaySheet> {
  late final Set<String> _keep = {...widget.kept};

  static const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  void _close(SickSheetAction action) => Navigator.of(
    context,
  ).pop<SickSheetResult>((action: action, keep: {..._keep}));

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final day = widget.day;
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '${widget.isSick ? 'Sick day' : 'Mark sick'}: '
              '${_weekdays[day.weekday - 1]} ${FreeDayPool.toIso(day)}',
              style: theme.textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(
              'Off = stands down for the day. Switch on any locker that '
              'should still apply; it then behaves exactly as on a normal '
              'day.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 8),
            for (final MapEntry(:key, :value) in sickLockerLabels.entries)
              SwitchListTile(
                key: ValueKey<String>('keep-$key'),
                contentPadding: EdgeInsets.zero,
                title: Text(value),
                value: _keep.contains(key),
                onChanged: (on) =>
                    setState(() => on ? _keep.add(key) : _keep.remove(key)),
              ),
            const SizedBox(height: 16),
            if (widget.isSick) ...[
              FilledButton(
                onPressed: () => _close(SickSheetAction.save),
                child: const Text('Save'),
              ),
              const SizedBox(height: 8),
              TextButton(
                style: TextButton.styleFrom(
                  foregroundColor: theme.colorScheme.error,
                ),
                onPressed: () => _close(SickSheetAction.clear),
                child: const Text('Clear sick day'),
              ),
            ] else
              FilledButton(
                onPressed: () => _close(SickSheetAction.mark),
                child: const Text('Mark sick'),
              ),
          ],
        ),
      ),
    );
  }
}
