import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/screens/day_calendar.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/dashed_slot.dart';

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
  final DayCalendar calendar;

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

  String _toDdMmYyyy(DateTime day) {
    final d = day.day.toString().padLeft(2, '0');
    final m = day.month.toString().padLeft(2, '0');
    return '$d.$m.${day.year}';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              const Icon(Icons.event_available),
              const SizedBox(width: 8),
              Text(
                '$remaining/${FreeDayPool.annualBudget}',
                style: theme.textTheme.displayMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          Text(
            '$year',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 8),
          if (status.isNotEmpty) ...[
            const SizedBox(height: 16),
            StatusCue(semanticLabel: status),
          ],
          const SizedBox(height: 16),
          calendar,
          const SizedBox(height: 24),
          Row(
            children: [
              Icon(
                Icons.upcoming,
                color: theme.colorScheme.onSurfaceVariant,
                semanticLabel: 'Booked ahead',
              ),
            ],
          ),
          const SizedBox(height: 8),
          if (upcoming.isEmpty)
            const SpokenLabel(
              semanticLabel: 'None. Tap a date above to book one.',
              child: DashedSlot(),
            ),
          for (final entry in upcoming)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(_toDdMmYyyy(entry.day)),
              subtitle: entry.reason.isEmpty
                  ? null
                  : KeyedSubtree(
                      key: ValueKey<String>(
                        'content:reason-${FreeDayPool.toIso(entry.day)}',
                      ),
                      child: Text(entry.reason),
                    ),
              trailing: IconButton(
                key: ValueKey<String>(
                  'release-${FreeDayPool.toIso(entry.day)}',
                ),
                icon: const Icon(Icons.event_busy, semanticLabel: 'Release'),
                onPressed: busy ? null : () => onRelease(entry.day),
              ),
            ),
        ],
      ),
    );
  }
}
