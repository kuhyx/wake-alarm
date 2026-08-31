import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';

/// The three-step progress list shown while the room proof is incomplete.
///
/// Showing every stage up front — including the ones not yet live — is
/// deliberate: a half-asleep user needs to see that a second tag is coming,
/// not discover it after walking back to bed.
class RingChecklist extends StatelessWidget {
  /// Creates a checklist reflecting [gate]'s current stage.
  const RingChecklist({required this.gate, super.key});

  /// The sequence being displayed.
  final DismissGate gate;

  static const List<(DismissStage, String)> _rows = <(DismissStage, String)>[
    (DismissStage.tag1, 'Tap tag 1'),
    (DismissStage.steps, 'Walk 25 steps'),
    (DismissStage.tag2, 'Tap tag 2'),
  ];

  /// Whether [stage] has already been passed.
  bool _isDone(DismissStage stage) => stage.index < gate.stage.index;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        for (final (stage, label) in _rows)
          if (!(gate.bypassActive && stage != DismissStage.steps))
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                children: <Widget>[
                  Icon(
                    _isDone(stage)
                        ? Icons.check_circle
                        : Icons.radio_button_unchecked,
                    color: _isDone(stage)
                        ? theme.colorScheme.primary
                        : theme.disabledColor,
                  ),
                  const SizedBox(width: 12),
                  Text(
                    label,
                    style: gate.stage == stage
                        ? theme.textTheme.titleMedium
                        : theme.textTheme.bodyMedium,
                  ),
                ],
              ),
            ),
        if (gate.bypassActive)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(
              // This line persists; the status below it is overwritten by the
              // live step count within seconds, so the reason the tags went
              // away has to live here or the user never sees it.
              gate.awayActive
                  ? 'Away from home — the tags are elsewhere. Walk, then '
                        'answer ${gate.challengesRequired} questions.'
                  : 'Tags unavailable — walk, then answer '
                        '${gate.challengesRequired} questions instead.',
              style: theme.textTheme.bodyMedium,
            ),
          ),
      ],
    );
  }
}
