import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/weight_entry.dart';
import 'package:wake_alarm_sync/ui/spoken_label.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// The session's progress list: the weigh-in, then every leg with a tag.
///
/// Every remaining leg is shown up front, as on the ring screen: someone
/// half-asleep has to see that the desk tag is still coming before they sit
/// on the bed. Skipped legs (no tag registered) are not listed at all —
/// they were never required.
class SessionChecklist extends StatelessWidget {
  /// Creates a checklist reflecting [session] at [now].
  const SessionChecklist({required this.session, required this.now, super.key});

  /// The session being displayed.
  final MorningSession session;

  /// The instant the list is drawn at; unused today, kept for countdowns.
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final weighed = session.weightKg != null || session.pendingWeightKg != null;
    final current = session.currentLeg;
    final rows = <Widget>[
      _WeighInRow(
        session: session,
        weighed: weighed,
        current: current,
        theme: theme,
      ),
      for (final leg in SessionLeg.values)
        if (session.passedHow[leg] != LegPass.skipped)
          _LegRow(
            session: session,
            leg: leg,
            current: current,
            theme: theme,
            weighed: weighed,
          ),
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: rows);
  }
}

class _WeighInRow extends StatelessWidget {
  const _WeighInRow({
    required this.session,
    required this.weighed,
    required this.current,
    required this.theme,
  });

  final MorningSession session;
  final bool weighed;
  final SessionLeg? current;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    final live = !weighed && current == SessionLeg.bathroomIn;
    return SpokenLabel(
      semanticLabel: weighed
          ? session.energy == null
                ? 'Weight logged'
                : 'Weigh in — ${session.weightKg ?? session.pendingWeightKg} kg · energy ${session.energy}/$maxEnergy'
          : 'Weigh in',
      key: const ValueKey<String>('session-row-weigh'),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          children: <Widget>[
            Icon(
              weighed ? Icons.check_circle : Icons.radio_button_unchecked,
              color: weighed ? theme.colorScheme.primary : theme.disabledColor,
            ),
            const SizedBox(width: 12),
            Icon(
              Icons.monitor_weight_outlined,
              size: 32,
              color: live ? theme.colorScheme.primary : null,
            ),
            const SizedBox(width: 12),
            if (weighed) ...<Widget>[
              Text('${session.weightKg ?? session.pendingWeightKg}'),
              if (session.energy != null) ...<Widget>[
                const SizedBox(width: 8),
                const Icon(Icons.bolt, size: 18),
                Text('${session.energy}/$maxEnergy'),
              ],
            ],
          ],
        ),
      ),
    );
  }
}

class _LegRow extends StatelessWidget {
  const _LegRow({
    required this.session,
    required this.leg,
    required this.current,
    required this.theme,
    required this.weighed,
  });

  final MorningSession session;
  final SessionLeg leg;
  final SessionLeg? current;
  final ThemeData theme;
  final bool weighed;

  @override
  Widget build(BuildContext context) {
    final done = session.passedAt.containsKey(leg);
    final how = session.passedHow[leg];
    final live = leg == current && (leg != SessionLeg.bathroomIn || weighed);
    final bypassed = how == LegPass.bypassed;

    final statusColors = theme.extension<AppStatusColors>();
    final warningColor = statusColors?.warning ?? Colors.amber;

    IconData frontIcon;
    if (done) {
      frontIcon = bypassed ? Icons.timer_off : Icons.check_circle;
    } else {
      frontIcon = Icons.radio_button_unchecked;
    }

    Color frontColor;
    if (done) {
      frontColor = bypassed ? warningColor : theme.colorScheme.primary;
    } else {
      frontColor = theme.disabledColor;
    }

    return SpokenLabel(
      semanticLabel: how == null ? leg.label : _semanticLabel(leg, how),
      key: ValueKey<String>('session-row-${leg.name}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          children: <Widget>[
            Icon(frontIcon, color: frontColor, size: live ? 32 : 24),
            const SizedBox(width: 12),
            _legIcon(
              leg,
              size: live ? 32 : 24,
              color: live ? theme.colorScheme.primary : null,
            ),
            const SizedBox(width: 12),
            const Icon(Icons.nfc, size: 18),
          ],
        ),
      ),
    );
  }

  String _semanticLabel(SessionLeg leg, LegPass how) {
    if (how == LegPass.bypassed) return '${leg.label} (skipped by the clock)';
    if (leg == SessionLeg.bathroomIn && !session.bathroomTagRequired) {
      return 'Weight logged';
    }
    return leg.label;
  }

  Widget _legIcon(SessionLeg leg, {double size = 24, Color? color}) {
    return Icon(_legIconData(leg), size: size, color: color);
  }

  IconData _legIconData(SessionLeg leg) {
    switch (leg) {
      case SessionLeg.bathroomIn:
        return Icons.bathroom_outlined;
      case SessionLeg.showerDone:
        return Icons.shower;
      case SessionLeg.dressed:
        return Icons.checkroom;
      case SessionLeg.atDesk:
        return Icons.desk;
    }
  }
}
