import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';
import 'package:wake_alarm_sync/ui/spoken_label.dart';

/// The question half of the ring screen, shown once the walk is proven.
class RingChallenge extends StatelessWidget {
  /// Creates the challenge view for [challenge].
  const RingChallenge({
    required this.challenge,
    required this.controller,
    required this.passed,
    required this.total,
    required this.onSubmit,
    super.key,
  });

  /// The question currently being asked.
  final Challenge challenge;

  /// Controller for the answer field, owned by the ring screen.
  final TextEditingController controller;

  /// How many questions have been answered correctly so far.
  final int passed;

  /// How many are needed in total; higher once the bypass is active.
  final int total;

  /// Called when the user submits an answer.
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    const answerWords = 'Answer';
    return Column(
      children: <Widget>[
        SpokenLabel(
          semanticLabel: 'Question ${passed + 1} of $total',
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text('${passed + 1}/$total', style: theme.textTheme.labelLarge),
              const SizedBox(width: 8),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: List.generate(total, (i) {
                  final filled = i < passed;
                  final current = i == passed;
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 2),
                    child: Icon(
                      filled
                          ? Icons.circle
                          : current
                          ? Icons.circle_outlined
                          : Icons.circle_outlined,
                      size: 8,
                      color: filled
                          ? colorScheme.primary
                          : current
                          ? colorScheme.primary
                          : colorScheme.onSurfaceVariant,
                    ),
                  );
                }),
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        SpokenLabel(
          semanticLabel: challenge.hint,
          child: Icon(
            _kindIcon(challenge.kind),
            size: 40,
            color: colorScheme.primary,
          ),
        ),
        const SizedBox(height: 12),
        KeyedSubtree(
          key: const ValueKey<String>('content:challenge'),
          child: Text(
            challenge.display,
            textAlign: TextAlign.center,
            style: theme.textTheme.displaySmall,
          ),
        ),
        const SizedBox(height: 16),
        MergeSemantics(
          child: Semantics(
            label: answerWords,
            child: TextField(
              controller: controller,
              autofocus: true,
              textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(prefixIcon: Icon(Icons.edit)),
              onSubmitted: (_) => onSubmit(),
            ),
          ),
        ),
        const SizedBox(height: 16),
        FilledButton(
          key: const Key('ring-submit'),
          style: FilledButton.styleFrom(minimumSize: const Size(160, 48)),
          onPressed: onSubmit,
          child: const Icon(Icons.check, semanticLabel: 'Submit'),
        ),
      ],
    );
  }
}

IconData _kindIcon(ChallengeKind kind) {
  switch (kind) {
    case ChallengeKind.math:
      return Icons.calculate_outlined;
    case ChallengeKind.sort:
      return Icons.trending_up;
    case ChallengeKind.sequence:
      return Icons.more_horiz;
    case ChallengeKind.reverse:
      return Icons.swap_horiz;
  }
}

/// Logs [challenge] so a hardware test can be scripted.
///
/// Debug aid only: the answer is already on screen for whoever is holding
/// the phone, so this leaks nothing the user cannot see. `debugPrint`
/// rather than `developer.log` so it reaches logcat, which is what the
/// emulator harness reads the answer from.
void logChallenge(Challenge challenge, DismissGate gate) {
  debugPrint(
    'WakeAlarmRing: challenge kind=${challenge.kind.name} '
    'display="${challenge.display}" answer=${challenge.answer} '
    '${gate.challengesPassed}/${gate.challengesRequired}',
  );
}
