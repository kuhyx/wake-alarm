import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/alarm_ramp.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';

/// A month grid of one day pool (free days or sick days), one tap per day.
///
/// Adapted from punchme's `FreeDayCalendar` (Monday-first grid, dumb cells);
/// punchme's own free days are a separate concept and are not read here.
/// Deciding what a tap *means* stays with the screen: this only reports which
/// date was tapped. Past days are always inert. Today is inert too unless
/// [todayTappable]: releasing a free day that has already started still
/// spends it, so the free-day grid does not offer it, while a sick day can
/// be marked or cleared for today.
class DayCalendar extends StatelessWidget {
  /// Creates a grid over [month].
  const DayCalendar({
    required this.month,
    required this.today,
    required this.isMarked,
    required this.busy,
    required this.onTapDay,
    required this.onMonth,
    this.firstMonth,
    this.lastMonth,
    this.todayTappable = false,
    this.keyPrefix = 'free-day',
    this.markColor,
    this.onMarkColor,
    super.key,
  });

  /// The month on display; only its year and month are read.
  final DateTime month;

  /// The reference date: everything before it is read-only, and it too
  /// unless [todayTappable].
  final DateTime today;

  /// Whether a date is currently marked in the pool.
  final bool Function(DateTime day) isMarked;

  /// Whether [today] itself can be tapped.
  final bool todayTappable;

  /// Each cell's key is `<keyPrefix>-<yyyy-MM-dd>`.
  final String keyPrefix;

  /// A marked day's fill; null means the theme's primary (free days).
  final Color? markColor;

  /// Text on [markColor]; null means the theme's onPrimary.
  final Color? onMarkColor;

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
            for (var day = 1; day <= total; day++) _cell(theme, day),
          ],
        ),
      ],
    );
  }

  Widget _cell(ThemeData theme, int day) {
    final date = DateTime(month.year, month.month, day);
    final open = date.isAfter(today) || (todayTappable && date == today);
    return DayCell(
      key: ValueKey<String>('$keyPrefix-${FreeDayPool.toIso(date)}'),
      day: day,
      isMarked: isMarked(date),
      isWorkday: isWorkday(date),
      isPast: !open,
      markColor: markColor ?? theme.colorScheme.primary,
      onMarkColor: onMarkColor ?? theme.colorScheme.onPrimary,
      onTap: open && !busy ? () => onTapDay(date) : null,
    );
  }
}

/// One day box: renders the state it is handed and reports taps.
class DayCell extends StatelessWidget {
  /// Creates a cell for [day] of the month.
  const DayCell({
    required this.day,
    required this.isMarked,
    required this.isWorkday,
    required this.isPast,
    required this.markColor,
    required this.onMarkColor,
    required this.onTap,
    super.key,
  });

  /// The day of the month, as shown in the box.
  final int day;

  /// Whether this date is marked in the pool.
  final bool isMarked;

  /// A marked day's fill.
  final Color markColor;

  /// Text on [markColor].
  final Color onMarkColor;

  /// Whether this date is a weekly workday (Tue/Wed/Thu), shaded.
  final bool isWorkday;

  /// Whether this date is read-only (past, or today on the free grid).
  final bool isPast;

  /// Called on tap, or null when the cell is inert.
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    // Past days keep their marker, faded: the record is history, not a
    // choice still open.
    final fade = isPast ? 0.38 : 1.0;
    final background = isMarked
        ? markColor.withValues(alpha: fade)
        : isWorkday
        ? colors.surfaceContainerHigh
        : null;
    final foreground = isMarked
        ? onMarkColor
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
            fontWeight: isMarked ? FontWeight.w600 : FontWeight.normal,
          ),
        ),
      ),
    );
  }
}
