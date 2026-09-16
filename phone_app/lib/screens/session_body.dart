import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/session_checklist.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';

/// The session screen's body: the checklist, the weigh-in field, the clocks.
///
/// Stateless, taking plain values — the screen keeps the state and the
/// ordering, which is where the ring's bugs lived.
class SessionBody extends StatelessWidget {
  /// Creates the body from already-resolved state.
  const SessionBody({
    required this.session,
    required this.now,
    required this.controller,
    required this.status,
    required this.onSubmitWeight,
    super.key,
  });

  /// The session being displayed.
  final MorningSession session;

  /// The instant the clocks are drawn at.
  final DateTime now;

  /// The weigh-in field's controller.
  final TextEditingController controller;

  /// The status line.
  final String status;

  /// Called when the user submits a weight.
  final VoidCallback onSubmitWeight;

  /// Whether the weigh-in field is live: first leg, nothing typed yet.
  bool get _awaitingWeight =>
      session.currentLeg == SessionLeg.bathroomIn &&
      session.weightKg == null &&
      session.pendingWeightKg == null;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final leg = session.currentLeg;
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text('Stay up', style: theme.textTheme.headlineMedium),
              const SizedBox(height: 4),
              Text(
                'The alarm is off. It comes back if a step below is missed, '
                'or if the phone lies still.',
                style: theme.textTheme.bodyMedium,
              ),
              const SizedBox(height: 24),
              SessionChecklist(session: session, now: now),
              const SizedBox(height: 24),
              if (_awaitingWeight) ...<Widget>[
                TextField(
                  controller: controller,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: const InputDecoration(
                    labelText: 'Weight (kg)',
                    border: OutlineInputBorder(),
                  ),
                  onSubmitted: (_) => onSubmitWeight(),
                ),
                const SizedBox(height: 12),
                FilledButton(
                  onPressed: onSubmitWeight,
                  child: const Text('Log weight'),
                ),
                const SizedBox(height: 16),
              ],
              if (leg != null)
                Text(
                  _deadlineLine(leg),
                  textAlign: TextAlign.center,
                  style: theme.textTheme.titleMedium,
                ),
              const SizedBox(height: 8),
              Text(
                'Re-rings: ${session.reRings}/${MorningSession.maxReRings}',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 16),
              if (status.isNotEmpty)
                Text(
                  status,
                  textAlign: TextAlign.center,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyLarge,
                ),
            ],
          ),
        ),
      ),
    );
  }

  String _deadlineLine(SessionLeg leg) {
    final soonest = session.earliest(leg);
    if (soonest != null && now.isBefore(soonest)) {
      return 'Shower — tag counts in ${_mmss(soonest.difference(now))}';
    }
    final deadline = session.deadline(leg);
    if (now.isBefore(deadline)) {
      return 'Alarm returns in ${_mmss(deadline.difference(now))}';
    }
    return 'Deadline passed';
  }

  static String _mmss(Duration d) {
    final m = d.inMinutes.toString().padLeft(2, '0');
    final s = (d.inSeconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }
}
