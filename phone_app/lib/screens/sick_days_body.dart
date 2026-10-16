import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/day_calendar.dart';
import 'package:wake_alarm_sync/screens/sick_day_sheet.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// The sick-day picker's body: what a sick day does, the status line, the
/// month calendar and the sick days still ahead.
///
/// Stateless and fed plain values, like `FreeDaysBody`: the screen owns the
/// pool and the sync ordering, this only draws. No count and no budget --
/// sick days have none.
class SickDaysBody extends StatelessWidget {
  /// Creates the body from already-resolved state.
  const SickDaysBody({
    required this.upcoming,
    required this.status,
    required this.cache,
    required this.refused,
    required this.calendar,
    required this.keptOf,
    super.key,
  });

  /// The lockers a sick day keeps active, for its line in the list.
  final Set<String> Function(DateTime day) keptOf;

  /// The month grid, built by the screen, which owns the displayed month.
  final DayCalendar calendar;

  /// Sick days from today on, ascending.
  final List<DateTime> upcoming;

  /// The status line; may be a raw `Error: …`.
  final String status;

  /// The native ring-path cache, read back (`Alarm cache: …`).
  final String cache;

  /// Whether [status] is a refused tap, drawn like an error.
  final bool refused;

  static const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  String _label(DateTime day) =>
      '${_weekdays[day.weekday - 1]} ${FreeDayPool.toIso(day)}';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurfaceVariant;
    final statusColors = theme.extension<AppStatusColors>()!;
    final failed = refused || status.contains('Error');
    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'Tap a day to mark it sick and choose which lockers still '
            'apply; tap a sick day to change them or clear it. Today or '
            'later only. No limit and no reason needed.',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: 8),
          Text(
            'On a sick day every locker left off stands down: no alarm, no '
            'lock, and work left undone is dropped rather than carried '
            'forward. A locker switched on behaves as on a normal day; a dot '
            'marks a sick day that keeps one.',
            style: theme.textTheme.bodySmall?.copyWith(color: muted),
          ),
          if (status.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text(
              status,
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: failed ? theme.colorScheme.error : statusColors.success,
              ),
            ),
          ],
          if (cache.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(cache, style: TextStyle(color: muted)),
          ],
          const SizedBox(height: 16),
          calendar,
          const SizedBox(height: 24),
          Text('Marked sick', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          if (upcoming.isEmpty)
            Text('None ahead.', style: TextStyle(color: muted)),
          for (final day in upcoming)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(_label(day)),
              subtitle: switch (keptLabel(keptOf(day))) {
                '' => null,
                final kept => Text('Kept: $kept'),
              },
            ),
        ],
      ),
    );
  }
}
