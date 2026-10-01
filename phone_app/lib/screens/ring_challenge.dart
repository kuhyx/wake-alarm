import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';

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
    return Column(
      children: <Widget>[
        Text(
          'Question ${passed + 1} of $total',
          style: theme.textTheme.labelLarge,
        ),
        const SizedBox(height: 8),
        Text(challenge.hint, style: theme.textTheme.bodyLarge),
        const SizedBox(height: 12),
        Text(
          // Always visible: a challenge that hides itself is unsolvable when
          // the user reaches the screen having walked in from another room.
          challenge.display,
          textAlign: TextAlign.center,
          style: theme.textTheme.displaySmall,
        ),
        const SizedBox(height: 16),
        TextField(
          controller: controller,
          autofocus: true,
          textCapitalization: TextCapitalization.characters,
          decoration: const InputDecoration(labelText: 'Answer'),
          onSubmitted: (_) => onSubmit(),
        ),
        const SizedBox(height: 16),
        FilledButton(onPressed: onSubmit, child: const Text('Submit')),
      ],
    );
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
