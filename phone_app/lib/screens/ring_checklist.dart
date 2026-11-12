import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';
import 'package:wake_alarm_sync/services/room_proof.dart';
import 'package:wake_alarm_sync/ui/spoken_label.dart';

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
    final colorScheme = theme.colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        for (final (stage, label) in _rows)
          if (!(gate.bypassActive && stage != DismissStage.steps))
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: SpokenLabel(
                semanticLabel: label,
                key: ValueKey<String>('ring-row-${stage.name}'),
                child: Row(
                  children: <Widget>[
                    Icon(
                      _isDone(stage)
                          ? Icons.check_circle
                          : Icons.radio_button_unchecked,
                      color: _isDone(stage)
                          ? colorScheme.primary
                          : theme.disabledColor,
                      size: gate.stage == stage ? 32 : 24,
                    ),
                    const SizedBox(width: 12),
                    _stageGlyphs(stage, gate.stage == stage, colorScheme),
                  ],
                ),
              ),
            ),
        if (gate.bypassActive)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: SpokenLabel(
              semanticLabel: gate.awayActive
                  ? 'Away from home — the tags are elsewhere. Walk, then '
                        'answer ${gate.challengesRequired} questions.'
                  : 'Tags unavailable — walk, then answer '
                        '${gate.challengesRequired} questions instead.',
              key: const Key('ring-bypass'),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Icon(
                    gate.awayActive ? Icons.explore : Icons.block,
                    color: colorScheme.error,
                  ),
                  const Icon(Icons.arrow_forward, size: 16),
                  const Icon(Icons.directions_walk),
                  const Icon(Icons.arrow_forward, size: 16),
                  const Icon(Icons.quiz_outlined),
                  Text('${gate.challengesRequired}'),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _stageGlyphs(DismissStage stage, bool current, ColorScheme cs) {
    final primary = cs.primary;
    final muted = cs.onSurfaceVariant;
    final color = current ? primary : muted;
    final size = current ? 32.0 : 24.0;
    switch (stage) {
      case DismissStage.tag1:
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.nfc, size: size, color: color),
            Text(
              '1',
              style: TextStyle(fontSize: size, color: color),
            ),
          ],
        );
      case DismissStage.steps:
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.directions_walk, size: size, color: color),
            Text(
              '${RoomProof.requiredSteps}',
              style: TextStyle(fontSize: size, color: color),
            ),
          ],
        );
      case DismissStage.tag2:
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.nfc, size: size, color: color),
            Text(
              '2',
              style: TextStyle(fontSize: size, color: color),
            ),
          ],
        );
      case DismissStage.challenges:
      case DismissStage.done:
        return const SizedBox.shrink();
    }
  }
}
