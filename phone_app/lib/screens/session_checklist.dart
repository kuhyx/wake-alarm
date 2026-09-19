import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/weight_entry.dart';

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
    final rows = <(String, bool, bool)>[
      (
        'Weigh in${_kg(session)}',
        weighed,
        !weighed && current == SessionLeg.bathroomIn,
      ),
      for (final leg in SessionLeg.values)
        if (session.passedHow[leg] != LegPass.skipped)
          (
            _label(leg),
            session.passedAt.containsKey(leg),
            leg == current && (leg != SessionLeg.bathroomIn || weighed),
          ),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        for (final (label, done, live) in rows)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Row(
              children: <Widget>[
                Icon(
                  done ? Icons.check_circle : Icons.radio_button_unchecked,
                  color: done ? theme.colorScheme.primary : theme.disabledColor,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    label,
                    style: live
                        ? theme.textTheme.titleMedium
                        : theme.textTheme.bodyMedium,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }

  String _label(SessionLeg leg) {
    final how = session.passedHow[leg];
    if (how == LegPass.bypassed) return '${leg.label} (skipped by the clock)';
    if (leg == SessionLeg.bathroomIn && !session.bathroomTagRequired) {
      return 'Weight logged';
    }
    return leg.label;
  }

  static String _kg(MorningSession session) {
    final kg = session.weightKg ?? session.pendingWeightKg;
    if (kg == null) return '';
    final energy = session.energy;
    return energy == null
        ? ' — $kg kg'
        : ' — $kg kg · energy $energy/$maxEnergy';
  }
}
