import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/home_history_card.dart';
import 'package:wake_alarm_sync/screens/stakes_card.dart';

/// The two detail tiles under the alarm time: today's stakes and the last
/// week of mornings.
///
/// The home screen fits one phone screen with no scrolling, so these cards
/// moved behind a tap instead of stacking under the control. Each opens its
/// full card in a bottom sheet; nothing was dropped.
class HomeTiles extends StatelessWidget {
  /// Creates the tiles; [syncEpoch] and [busy] reach the cards they open.
  const HomeTiles({
    required this.syncEpoch,
    required this.busy,
    this.onEscaped,
    super.key,
  });

  /// Bumped after every sync; a sheet opened afterwards loads fresh data.
  final int syncEpoch;

  /// Disables the escape hatch while the screen is syncing.
  final bool busy;

  /// Called after the escape hatch was used, so the screen publishes it.
  final VoidCallback? onEscaped;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Expanded(
          child: _Tile(
            key: const Key('home-tile-stakes'),
            icon: Icons.gavel_outlined,
            label: "Today's stakes",
            sheet: StakesCard(
              key: ValueKey<String>('stakes-$syncEpoch'),
              busy: busy,
              onEscaped: onEscaped,
              emptyText: 'No stakes to show: the native side has not answered.',
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _Tile(
            key: const Key('home-tile-history'),
            icon: Icons.history,
            label: 'Last mornings',
            sheet: HomeHistoryCard(
              key: ValueKey<String>('history-$syncEpoch'),
              emptyText: 'No finished morning yet.',
            ),
          ),
        ),
      ],
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile({
    required this.icon,
    required this.label,
    required this.sheet,
    super.key,
  });

  final IconData icon;
  final String label;
  final Widget sheet;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      color: theme.colorScheme.surfaceContainerHigh,
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => showModalBottomSheet<void>(
          context: context,
          isScrollControlled: true,
          builder: (_) => SafeArea(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: sheet,
            ),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(icon, color: theme.colorScheme.onSurfaceVariant),
              const SizedBox(height: 8),
              Text(label, textAlign: TextAlign.center, maxLines: 1),
            ],
          ),
        ),
      ),
    );
  }
}
