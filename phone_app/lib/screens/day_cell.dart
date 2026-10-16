import 'package:flutter/material.dart';

Widget _dot(Color color) => Container(
  key: const ValueKey<String>('day-badge'),
  width: 6,
  height: 6,
  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
);

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
    this.badge = false,
    super.key,
  });

  /// Whether a small dot sits in the corner, in [onMarkColor].
  final bool badge;

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
        child: Stack(
          alignment: Alignment.center,
          children: [
            Text(
              '$day',
              style: TextStyle(
                color: foreground,
                fontWeight: isMarked ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
            if (badge) Positioned(top: 4, right: 4, child: _dot(foreground)),
          ],
        ),
      ),
    );
  }
}
