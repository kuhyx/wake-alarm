import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/screens/day_calendar.dart';
import 'package:wake_alarm_sync/screens/sick_day_sheet.dart';
import 'package:wake_alarm_sync/services/sick_day_keep.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/dashed_slot.dart';

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
    required this.cacheRead,
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

  /// The native ring-path cache, read back (list of ISO
  /// dates or null for unreadable).
  final List<String>? cache;

  /// Whether the cache has been read at least once.
  final bool cacheRead;

  /// Whether [status] is a refused tap, drawn like an error.
  final bool refused;

  String _toDdMmYyyy(DateTime day) {
    final d = day.day.toString().padLeft(2, '0');
    final m = day.month.toString().padLeft(2, '0');
    return '$d.$m.${day.year}';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final failed = refused || status.contains('Error');
    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (status.isNotEmpty) ...[
            const SizedBox(height: 16),
            StatusCue(
              semanticLabel: status,
              kind: failed ? CueKind.error : null,
            ),
          ],
          if (cacheRead) ...[
            const SizedBox(height: 8),
            Row(
              children: [
                Icon(
                  Icons.memory,
                  size: 16,
                  semanticLabel: _cacheSemanticLabel,
                ),
                const SizedBox(width: 8),
                _buildCacheContent(theme),
              ],
            ),
          ],
          const SizedBox(height: 16),
          calendar,
          const SizedBox(height: 24),
          const Row(
            children: [Icon(Icons.sick_outlined, semanticLabel: 'Marked sick')],
          ),
          const SizedBox(height: 8),
          if (upcoming.isEmpty)
            const SpokenLabel(
              semanticLabel: 'None ahead.',
              child: DashedSlot(),
            ),
          for (final day in upcoming)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(_toDdMmYyyy(day)),
              subtitle: _keptIcons(keptOf(day)),
            ),
        ],
      ),
    );
  }

  String get _cacheSemanticLabel {
    if (cache == null) return 'Alarm cache: unreadable';
    if (cache!.isEmpty) return 'Alarm cache: none';
    return 'Alarm cache: ${cache!.join(', ')}';
  }

  Widget _buildCacheContent(ThemeData theme) {
    if (cache == null) {
      return Icon(
        Icons.error_outline,
        color: theme.colorScheme.error,
        size: 16,
      );
    }
    if (cache!.isEmpty) {
      return Icon(
        Icons.check,
        size: 16,
        color: theme.colorScheme.onSurfaceVariant,
      );
    }
    return Text(
      cache!.join(', '),
      style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
    );
  }

  Widget? _keptIcons(Set<String> kept) {
    if (kept.isEmpty) return null;
    return Row(
      children: [
        for (final locker in SickLocker.all)
          if (kept.contains(locker))
            Padding(
              padding: const EdgeInsets.only(right: 4),
              child: Icon(sickLockerIcons[locker], size: 16),
            ),
      ],
    );
  }
}
