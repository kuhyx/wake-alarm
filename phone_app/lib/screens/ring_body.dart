import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/ring_challenge.dart';
import 'package:wake_alarm_sync/screens/ring_checklist.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';

/// The ring screen's body: the checklist, or the live challenge, plus status.
///
/// Split out of `ring_screen.dart` for the 250-line cap, following
/// `home_body.dart`. Deliberately stateless: the screen keeps the clocks, the
/// gate and the ordering rules, which is where the bugs lived.
class RingBody extends StatelessWidget {
  /// Creates the body from already-resolved state.
  const RingBody({
    required this.gate,
    required this.challenge,
    required this.controller,
    required this.status,
    required this.onSubmit,
    super.key,
  });

  /// The sequence being displayed.
  final DismissGate gate;

  /// The challenge shown once the challenge stage is live.
  final Challenge challenge;

  /// Controller for the answer field.
  final TextEditingController controller;

  /// The status line under the body.
  final String status;

  /// Called when an answer is submitted.
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final inChallenges = gate.stage == DismissStage.challenges;
    return PopScope(
      // The alarm cannot be escaped with back; dismissing is the only way out.
      canPop: false,
      child: Scaffold(
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                Text('Wake up', style: theme.textTheme.headlineMedium),
                const SizedBox(height: 24),
                if (inChallenges)
                  RingChallenge(
                    challenge: challenge,
                    controller: controller,
                    passed: gate.challengesPassed,
                    total: gate.challengesRequired,
                    onSubmit: onSubmit,
                  )
                else
                  RingChecklist(gate: gate),
                const SizedBox(height: 16),
                Text(status, style: theme.textTheme.bodyMedium),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
