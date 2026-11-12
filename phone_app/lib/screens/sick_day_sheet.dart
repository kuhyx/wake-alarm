import 'package:flutter/foundation.dart';
import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_keep.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';

export 'package:wake_alarm_sync/screens/sick_day_sheet.dart';

/// What each locker is called on screen, in `sickdays.LOCKERS` order.
const sickLockerLabels = <String, String>{
  SickLocker.workout: 'Workout lock',
  SickLocker.leetcode: 'LeetCode',
  SickLocker.book: 'Book',
  SickLocker.diet: 'Diet',
  SickLocker.alarm: 'Wake alarm',
};

/// Icons for each locker, matching [sickLockerLabels] order.
const sickLockerIcons = <String, IconData>{
  SickLocker.workout: Icons.fitness_center,
  SickLocker.leetcode: Icons.code,
  SickLocker.book: Icons.menu_book,
  SickLocker.diet: Icons.restaurant,
  SickLocker.alarm: Icons.alarm,
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

  String _toDdMmYyyy(DateTime day) {
    final d = day.day.toString().padLeft(2, '0');
    final m = day.month.toString().padLeft(2, '0');
    return '$d.$m.${day.year}';
  }

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
            Row(
              children: [
                const Icon(Icons.sick_outlined),
                const SizedBox(width: 8),
                Text(_toDdMmYyyy(day), style: theme.textTheme.titleMedium),
              ],
            ),
            const SizedBox(height: 8),
            for (final MapEntry(:key, :value) in sickLockerLabels.entries)
              SwitchListTile(
                key: ValueKey<String>('keep-$key'),
                contentPadding: EdgeInsets.zero,
                title: Icon(sickLockerIcons[key], semanticLabel: value),
                value: _keep.contains(key),
                onChanged: (on) =>
                    setState(() => on ? _keep.add(key) : _keep.remove(key)),
              ),
            const SizedBox(height: 16),
            if (widget.isSick) ...[
              FilledButton(
                key: const ValueKey<String>('sick-save'),
                onPressed: () => _close(SickSheetAction.save),
                child: const Icon(Icons.check, semanticLabel: 'Save'),
              ),
              const SizedBox(height: 8),
              TextButton(
                style: TextButton.styleFrom(
                  foregroundColor: theme.colorScheme.error,
                ),
                key: const ValueKey<String>('sick-clear'),
                onPressed: () => _close(SickSheetAction.clear),
                child: const Icon(
                  Icons.delete_outline,
                  semanticLabel: 'Clear sick day',
                ),
              ),
            ] else
              FilledButton(
                key: const ValueKey<String>('sick-mark'),
                onPressed: () => _close(SickSheetAction.mark),
                child: const Icon(Icons.sick, semanticLabel: 'Mark sick'),
              ),
          ],
        ),
      ),
    );
  }
}
