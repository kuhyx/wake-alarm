import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/alarm_ramp.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';

/// A month grid of the shared free-day pool, one tap per day.
///
/// Adapted from punchme's `FreeDayCalendar` (Monday-first grid, dumb cells);
/// punchme's own free days are a separate concept and are not read here.
/// Deciding what a tap *means* stays with the screen: this only reports which
/// future date was tapped. Past days and today are inert -- releasing a day
/// that has already started still spends it, so the grid does not offer it.
class FreeDayCalendar extends StatelessWidget {
  /// Creates a grid over [month].
  const FreeDayCalendar({
    required this.month,
    required this.today,
    required this.isFree,
    required this.busy,
    required this.onTapDay,
    required this.onMonth,
    this.firstMonth,
    this.lastMonth,
    super.key,
  });

  /// The month on display; only its year and month are read.
  final DateTime month;

  /// The reference date: it and everything before it are read-only.
  final DateTime today;

  /// Whether a date is currently free in the pool.
  final bool Function(DateTime day) isFree;

  /// Whether a sync is in flight, which makes every day inert.
  final bool busy;

  /// Called with a tapped future date.
  final void Function(DateTime day) onTapDay;

  /// Called with the month to show after an arrow tap.
  final void Function(DateTime month) onMonth;

  /// Earliest month the back arrow reaches; null means no limit.
  final DateTime? firstMonth;

  /// Latest month the forward arrow reaches; null means no limit.
  final DateTime? lastMonth;

  static const _labels = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
  static const _months = [
    'January', 'February', 'March', 'April', 'May', 'June', 'July', //
    'August', 'September', 'October', 'November', 'December',
  ];

  bool _before(DateTime a, DateTime b) =>
      a.year < b.year || (a.year == b.year && a.month < b.month);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final first = firstMonth;
    final last = lastMonth;
    final canBack = first == null || _before(first, month);
    final canForward = last == null || _before(month, last);
    final blanks = DateTime(month.year, month.month).weekday - 1;
    final total = DateTime(month.year, month.month + 1, 0).day;
    return Column(
      children: [
        Row(
          children: [
            IconButton(
              icon: const Icon(Icons.chevron_left),
              tooltip: 'Previous month',
              onPressed: canBack
                  ? () => onMonth(DateTime(month.year, month.month - 1))
                  : null,
            ),
            Expanded(
              child: Text(
                '${_months[month.month - 1]} ${month.year}',
                textAlign: TextAlign.center,
                style: theme.textTheme.titleMedium,
              ),
            ),
            IconButton(
              icon: const Icon(Icons.chevron_right),
              tooltip: 'Next month',
              onPressed: canForward
                  ? () => onMonth(DateTime(month.year, month.month + 1))
                  : null,
            ),
          ],
        ),
        Row(
          children: [
            for (final label in _labels)
              Expanded(
                child: Center(
                  child: Text(
                    label,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: 4),
        GridView.count(
          crossAxisCount: DateTime.daysPerWeek,
          shrinkWrap: true,
          // The screen's ListView owns scrolling.
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 4,
          crossAxisSpacing: 4,
          children: [
            for (var i = 0; i < blanks; i++) const SizedBox.shrink(),
            for (var day = 1; day <= total; day++) _cell(day),
          ],
        ),
      ],
    );
  }

  Widget _cell(int day) {
    final date = DateTime(month.year, month.month, day);
    final future = date.isAfter(today);
    return FreeDayCell(
      key: ValueKey<String>('free-day-${FreeDayPool.toIso(date)}'),
      day: day,
      isFree: isFree(date),
      isWorkday: isWorkday(date),
      isPast: !future,
      onTap: future && !busy ? () => onTapDay(date) : null,
    );
  }
}

/// One day box: renders the state it is handed and reports taps.
class FreeDayCell extends StatelessWidget {
  /// Creates a cell for [day] of the month.
  const FreeDayCell({
    required this.day,
    required this.isFree,
    required this.isWorkday,
    required this.isPast,
    required this.onTap,
    super.key,
  });

  /// The day of the month, as shown in the box.
  final int day;

  /// Whether this date is a free day.
  final bool isFree;

  /// Whether this date is a weekly workday (Tue/Wed/Thu), shaded.
  final bool isWorkday;

  /// Whether this date is today or earlier, and so read-only.
  final bool isPast;

  /// Called on tap, or null when the cell is inert.
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    // Past days keep their marker, faded: the record is history, not a
    // choice still open.
    final fade = isPast ? 0.38 : 1.0;
    final background = isFree
        ? colors.primary.withValues(alpha: fade)
        : isWorkday
        ? colors.surfaceContainerHigh
        : null;
    final foreground = isFree
        ? colors.onPrimary
        : colors.onSurface.withValues(alpha: fade);
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(
          '$day',
          style: TextStyle(
            color: foreground,
            fontWeight: isFree ? FontWeight.w600 : FontWeight.normal,
          ),
        ),
      ),
    );
  }
}
