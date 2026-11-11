import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/day_cell.dart';
import 'package:wake_alarm_sync/services/alarm_ramp.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';

export 'package:wake_alarm_sync/screens/day_cell.dart';

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
    this.hasBadge,
    super.key,
  });

  /// Whether a marked date carries a dot (a sick day keeping lockers);
  /// null means never.
  final bool Function(DateTime day)? hasBadge;

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

  bool _before(DateTime a, DateTime b) =>
      a.year < b.year || (a.year == b.year && a.month < b.month);

  Widget _weekdayDot(BuildContext context, int index) {
    final theme = Theme.of(context);
    final isWeekend = index == 5 || index == 6;
    return Container(
      width: isWeekend ? 8 : 6,
      height: isWeekend ? 8 : 6,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: isWeekend
            ? theme.colorScheme.primary
            : theme.colorScheme.onSurfaceVariant,
      ),
    );
  }

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
              icon: const Icon(
                Icons.chevron_left,
                semanticLabel: 'Previous month',
              ),
              onPressed: canBack
                  ? () => onMonth(DateTime(month.year, month.month - 1))
                  : null,
            ),
            Expanded(
              child: Text(
                '${month.month.toString().padLeft(2, '0')}/${month.year}',
                textAlign: TextAlign.center,
                style: theme.textTheme.titleMedium,
              ),
            ),
            IconButton(
              icon: const Icon(
                Icons.chevron_right,
                semanticLabel: 'Next month',
              ),
              onPressed: canForward
                  ? () => onMonth(DateTime(month.year, month.month + 1))
                  : null,
            ),
          ],
        ),
        Row(
          children: [
            for (var i = 0; i < 7; i++)
              Expanded(child: Center(child: _weekdayDot(context, i))),
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
      badge: hasBadge?.call(date) ?? false,
      isWorkday: isWorkday(date),
      isPast: !open,
      markColor: markColor ?? theme.colorScheme.primary,
      onMarkColor: onMarkColor ?? theme.colorScheme.onPrimary,
      onTap: open && !busy ? () => onTapDay(date) : null,
    );
  }
}
