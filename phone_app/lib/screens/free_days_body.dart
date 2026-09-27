import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/free_day_calendar.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// One upcoming free day, as the list shows it.
typedef UpcomingFreeDay = ({DateTime day, String reason});

/// The picker's body: the year's budget, the month calendar, the upcoming
/// days and the status line.
///
/// Stateless and fed plain values, like `HomeBody`: the screen owns the pool
/// and the sync ordering, this only draws.
class FreeDaysBody extends StatelessWidget {
  /// Creates the body from already-resolved state.
  const FreeDaysBody({
    required this.year,
    required this.remaining,
    required this.upcoming,
    required this.status,
    required this.busy,
    required this.onRelease,
    required this.calendar,
    super.key,
  });

  /// The month grid, built by the screen, which owns the displayed month.
  final FreeDayCalendar calendar;

  /// The calendar year the budget line describes.
  final int year;

  /// Days left in [year].
  final int remaining;

  /// Free days from today on, ascending.
  final List<UpcomingFreeDay> upcoming;

  /// The status line; may be a raw `Error: …`.
  final String status;

  /// Whether a sync is in flight, disabling the release buttons.
  final bool busy;

  /// Called when the user gives a day back.
  final void Function(DateTime day) onRelease;

  static const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  String _label(DateTime day) =>
      '${_weekdays[day.weekday - 1]} ${FreeDayPool.toIso(day)}';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final statusColors = theme.extension<AppStatusColors>()!;
    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            '$remaining of ${FreeDayPool.annualBudget}',
            style: theme.textTheme.displayMedium?.copyWith(
              fontWeight: FontWeight.bold,
            ),
          ),
          Text(
            'free days left in $year',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'On a free day nothing locks, nothing rings and nothing asks. '
            'Every app, at once.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          if (status.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text(
              status,
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: status.contains('Error')
                    ? theme.colorScheme.error
                    : statusColors.success,
              ),
            ),
          ],
          const SizedBox(height: 16),
          calendar,
          const SizedBox(height: 24),
          Text('Booked ahead', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          if (upcoming.isEmpty)
            Text(
              'None. Tap a date above to book one.',
              style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
            ),
          for (final entry in upcoming)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(_label(entry.day)),
              subtitle: entry.reason.isEmpty ? null : Text(entry.reason),
              trailing: TextButton(
                onPressed: busy ? null : () => onRelease(entry.day),
                child: const Text('Release'),
              ),
            ),
        ],
      ),
    );
  }
}
