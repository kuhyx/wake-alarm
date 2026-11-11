import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/energy_picker.dart';
import 'package:wake_alarm_sync/screens/session_checklist.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

const _weightSemantics = 'Weight (kg)';

/// The session screen's body: the checklist, the check-in, the clocks.
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
    required this.energy,
    required this.onSelectEnergy,
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

  /// The tapped energy level, or null.
  final int? energy;

  /// Called when an energy chip is tapped.
  final ValueChanged<int> onSelectEnergy;

  /// Called when the user submits a weight.
  final VoidCallback onSubmitWeight;

  /// Whether the weigh-in field is live: first leg, nothing typed yet.
  bool get _awaitingWeight =>
      session.currentLeg == SessionLeg.bathroomIn &&
      session.weightKg == null &&
      session.pendingWeightKg == null;

  @override
  Widget build(BuildContext context) {
    final leg = session.currentLeg;
    final reRingWords =
        'Re-rings: ${session.reRings}/${MorningSession.maxReRings}';
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              SessionChecklist(session: session, now: now),
              const SizedBox(height: 24),
              if (_awaitingWeight) ...<Widget>[
                EnergyPicker(selected: energy, onSelect: onSelectEnergy),
                const SizedBox(height: 12),
                MergeSemantics(
                  child: Semantics(
                    label: _weightSemantics,
                    child: TextField(
                      controller: controller,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                      decoration: const InputDecoration(
                        prefixIcon: Icon(Icons.monitor_weight_outlined),
                        border: OutlineInputBorder(),
                      ),
                      onSubmitted: (_) => onSubmitWeight(),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                FilledButton(
                  key: const Key('session-log-weight'),
                  onPressed: onSubmitWeight,
                  child: const Icon(Icons.check, semanticLabel: 'Log weight'),
                ),
                const SizedBox(height: 16),
              ],
              if (leg != null) ...<Widget>[
                SpokenLabel(
                  semanticLabel: _deadlineWords(leg),
                  child: _DeadlineRow(leg: leg, session: session, now: now),
                ),
                const SizedBox(height: 8),
              ],
              SpokenLabel(
                semanticLabel: reRingWords,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: <Widget>[
                    const Icon(Icons.replay, size: 16),
                    Text('${session.reRings}/${MorningSession.maxReRings}'),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Center(child: StatusCue(semanticLabel: status)),
            ],
          ),
        ),
      ),
    );
  }

  String _deadlineWords(SessionLeg leg) {
    final soonest = session.earliest(leg);
    if (soonest != null && now.isBefore(soonest)) {
      return 'Shower tag counts in ${_mmss(soonest.difference(now))}';
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

class _DeadlineRow extends StatelessWidget {
  const _DeadlineRow({
    required this.leg,
    required this.session,
    required this.now,
  });

  final SessionLeg leg;
  final MorningSession session;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final soonest = session.earliest(leg);
    if (soonest != null && now.isBefore(soonest)) {
      return Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          const Icon(Icons.shower),
          const Icon(Icons.hourglass_top),
          Text(_mmss(soonest.difference(now))),
        ],
      );
    }
    final deadline = session.deadline(leg);
    if (now.isBefore(deadline)) {
      return Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          const Icon(Icons.alarm),
          Text(_mmss(deadline.difference(now))),
        ],
      );
    }
    final statusColors = theme.extension<AppStatusColors>();
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        Icon(Icons.alarm_off, color: statusColors?.warning ?? Colors.amber),
      ],
    );
  }

  static String _mmss(Duration d) {
    final m = d.inMinutes.toString().padLeft(2, '0');
    final s = (d.inSeconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }
}
