import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/ring_challenge.dart';
import 'package:wake_alarm_sync/screens/ring_checklist.dart';
import 'package:wake_alarm_sync/services/alarm_policy.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';
import 'package:wake_alarm_sync/services/room_proof.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';

/// How often the live steps stage re-reads the step counter.
const Duration kStepPollInterval = Duration(seconds: 2);

/// The dismiss screen shown over the lockscreen while the alarm rings.
///
/// A strict sequence: tag 1, then the walk, then tag 2, then the challenges.
/// `DismissGate` owns the ordering; this widget owns the clocks and the UI.
class RingScreen extends StatefulWidget {
  /// Creates the ring screen; every dependency is injectable for tests.
  const RingScreen({
    super.key,
    this.scheduler,
    this.generator,
    this.clock,
  });

  /// Platform bridge; defaults to the real MethodChannel.
  final AlarmScheduler? scheduler;

  /// Challenge source; defaults to a secure-random generator.
  final ChallengeGenerator? generator;

  /// Time since the ring started; defaults to a real `Stopwatch`.
  ///
  /// Injectable because `Stopwatch` reads the wall clock, which
  /// `tester.pump()` does not advance — without this seam no widget test can
  /// reach the two-minute steps floor or the five-minute bypass.
  final Duration Function()? clock;

  @override
  State<RingScreen> createState() => _RingScreenState();
}

class _RingScreenState extends State<RingScreen> {
  late final AlarmScheduler _scheduler = widget.scheduler ?? AlarmScheduler();
  late final ChallengeGenerator _generator =
      widget.generator ?? ChallengeGenerator();
  late RoomProof _proof = RoomProof(scheduler: _scheduler);
  final DismissGate _gate = DismissGate();
  late Challenge _challenge = _generator.next();

  final TextEditingController _input = TextEditingController();
  final Stopwatch _stopwatch = Stopwatch()..start();
  late final Duration Function() _elapsed =
      widget.clock ?? () => _stopwatch.elapsed;
  Timer? _bypassTimer;
  Timer? _stepTimer;

  String _status = '';

  @override
  void initState() {
    super.initState();
    unawaited(_scheduler.beginStepCount());
    unawaited(_loadRoomProof());
    // The escape hatch. Set up before anything can fail, so a crash in the
    // settings load cannot leave an alarm with no way out.
    _bypassTimer = Timer(DismissGate.bypassAfter, _onBypassDue);
    _stepTimer = Timer.periodic(kStepPollInterval, (_) => _pollSteps());
  }

  /// Loads the registered tags and starts listening for NFC taps.
  Future<void> _loadRoomProof() async {
    final settings = await RoomProofSettings.load();
    final hasNfc = await _scheduler.hasNfc();
    if (!mounted) return;
    setState(() {
      _proof = RoomProof(scheduler: _scheduler, settings: settings);
      // Nothing to wait for: without NFC or without two distinct tags the
      // tag stages can never be satisfied, so making the user sit through
      // the full timer would be pure punishment for a config problem.
      if (!hasNfc || !settings.isComplete) {
        _gate.activateBypass();
        _status = hasNfc
            ? 'Register two NFC tags in Settings.'
            : 'NFC is off or unavailable.';
      }
    });
    _scheduler.onNfcTag(_onNfcTag);
  }

  void _onBypassDue() {
    if (!mounted) return;
    if (!_gate.activateBypass()) return;
    developer.log('bypass activated', name: 'WakeAlarmRing');
    setState(() => _status = 'Taking too long — tags skipped.');
  }

  void _onNfcTag(String tagId) {
    final slot = _gate.expectedTagSlot;
    if (slot == null) return;
    final result = _proof.checkNfc(tagId, slot: slot);
    developer.log(
      'nfc tag=$tagId slot=$slot satisfied=${result.satisfied} '
      'detail=${result.detail}',
      name: 'WakeAlarmRing',
    );
    if (!mounted) return;
    setState(() {
      // Only a pass moves the sequence. A wrong tag reports itself and
      // changes nothing — stages never un-latch.
      if (result.satisfied) _gate.passTagStage();
      _status = result.detail;
    });
    if (_gate.stage == DismissStage.challenges) _logChallenge();
  }

  /// Re-reads the step counter while the steps stage is live.
  ///
  /// Polled rather than button-driven: the walk to tag 1 has usually already
  /// banked the steps, so the only thing still binding is the elapsed-time
  /// floor. Making the user hunt for a button to discover that is friction
  /// without difficulty.
  Future<void> _pollSteps() async {
    if (_gate.stage != DismissStage.steps) return;
    final result = await _proof.checkSteps(_elapsed());
    if (!mounted || _gate.stage != DismissStage.steps) return;
    setState(() {
      if (result.satisfied) _gate.passStepsStage();
      _status = result.detail;
    });
    if (_gate.stage == DismissStage.challenges) _logChallenge();
  }

  /// Logs the current challenge so a hardware test can be scripted.
  ///
  /// Debug aid only: the answer is already on screen for whoever is holding
  /// the phone, so this leaks nothing the user cannot see.
  void _logChallenge() {
    developer.log(
      'challenge kind=${_challenge.kind.name} display="${_challenge.display}" '
      'answer=${_challenge.answer} '
      '${_gate.challengesPassed}/${_gate.challengesRequired}',
      name: 'WakeAlarmRing',
    );
  }

  @override
  void dispose() {
    _bypassTimer?.cancel();
    _stepTimer?.cancel();
    _scheduler.clearNfcListener();
    _input.dispose();
    _stopwatch.stop();
    super.dispose();
  }

  void _submit() {
    final correct = _challenge.accepts(_input.text);
    setState(() {
      _gate.recordChallenge(correct: correct);
      _input.clear();
      // A wrong answer costs the attempt only; the tally never falls back.
      if (_gate.isDone) {
        _status = 'Dismissed';
      } else {
        _status = correct
            ? 'Correct — next one'
            : 'Wrong — here is another one';
        _challenge = _generator.next();
      }
    });
    if (_gate.isDone) {
      unawaited(_finishDismiss());
    } else {
      _logChallenge();
    }
  }

  /// Stops the ring, then closes this screen.
  ///
  /// Ordered: the sound must stop even if closing the window fails.
  Future<void> _finishDismiss() async {
    developer.log('dismiss: stopping ring', name: 'WakeAlarmRing');
    await _scheduler.dismiss();
    // A one-shot earlier start applies to this alarm only. Without the reset
    // the first early morning would become permanent, with no way back to the
    // 08:00 baseline short of reinstalling — a ratchet with no reset is a
    // trap, not a defence.
    await AlarmPolicy.resetAfterFire();
    developer.log('dismiss: closing screen', name: 'WakeAlarmRing');
    await _scheduler.closeRingScreen();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final inChallenges = _gate.stage == DismissStage.challenges;
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
                    challenge: _challenge,
                    controller: _input,
                    passed: _gate.challengesPassed,
                    total: _gate.challengesRequired,
                    onSubmit: _submit,
                  )
                else
                  RingChecklist(gate: _gate),
                const SizedBox(height: 16),
                Text(_status, style: theme.textTheme.bodyMedium),
              ],
            ),
          ),
        ),
      ),
    );
  }

}
