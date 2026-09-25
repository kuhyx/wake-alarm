import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/ring_body.dart';
import 'package:wake_alarm_sync/services/alarm_policy.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';
import 'package:wake_alarm_sync/services/home_presence.dart';
import 'package:wake_alarm_sync/services/ring_startup.dart';
import 'package:wake_alarm_sync/services/room_proof.dart';
import 'package:wake_alarm_sync/services/session_handoff.dart';

/// How often the live steps stage re-reads the step counter.
const Duration kStepPollInterval = Duration(seconds: 2);

/// Route of the session screen the dismiss hands over to.
const String kSessionRoute = '/session';

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
    this.presence,
    this.handoff,
  });

  /// Platform bridge; defaults to the real MethodChannel.
  final AlarmScheduler? scheduler;

  /// Challenge source; defaults to a secure-random generator.
  final ChallengeGenerator? generator;

  /// Home-presence resolver; defaults to the real one.
  final HomePresence? presence;

  /// Starts or resumes the morning session; defaults to the real handoff.
  final SessionHandoff? handoff;

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
  late final HomePresence _presence =
      widget.presence ?? HomePresence(scheduler: _scheduler);
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

  /// Resolves presence and the registered tags, then applies the verdict.
  ///
  /// The ordering lives in `resolveRingStartup`; this only applies what it
  /// decided, in one `setState`.
  Future<void> _loadRoomProof() async {
    final startup = await resolveRingStartup(
      scheduler: _scheduler,
      presence: _presence,
    );
    if (!mounted) return;
    setState(() {
      _proof = RoomProof(scheduler: _scheduler, settings: startup.settings);
      switch (startup.skip) {
        case RingSkip.away:
          _gate.activateAwayProfile();
        case RingSkip.noTags:
          _gate.activateBypass();
        case RingSkip.none:
          break;
      }
      _status = startup.status;
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
  /// banked the steps, so on the normal path this passes on the first poll.
  /// The elapsed-time floor applies only under bypass, where no tag proved
  /// the walk and a shaken phone would otherwise count.
  Future<void> _pollSteps() async {
    if (_gate.stage != DismissStage.steps) return;
    final result = await _proof.checkSteps(
      _elapsed(),
      floor: _gate.bypassActive,
    );
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
  /// the phone, so this leaks nothing the user cannot see. `debugPrint`
  /// rather than `developer.log` so it reaches logcat, which is what the
  /// emulator harness reads the answer from.
  void _logChallenge() {
    debugPrint(
      'WakeAlarmRing: challenge kind=${_challenge.kind.name} '
      'display="${_challenge.display}" answer=${_challenge.answer} '
      '${_gate.challengesPassed}/${_gate.challengesRequired}',
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

  /// Stops the ring, then hands over to the session — or closes.
  ///
  /// Ordered: the sound must stop even if what follows fails. The session
  /// screen replaces this one *inside* the activity, so NFC reader mode and
  /// the kept-on screen carry over; closing only happens when there is no
  /// session to run (away from home, or a ring after the day's session).
  Future<void> _finishDismiss() async {
    developer.log('dismiss: stopping ring', name: 'WakeAlarmRing');
    await _scheduler.dismiss();
    // A one-shot earlier start applies to this alarm only. Without the reset
    // the first early morning would become permanent, with no way back to the
    // ramp baseline short of reinstalling — a ratchet with no reset is a
    // trap, not a defence.
    await AlarmPolicy.resetAfterFire();
    // dismiss() re-armed the *stored* time, i.e. the override just spent;
    // without re-arming the policy it rang again every day until home opened.
    final next = await AlarmPolicy.load();
    await _scheduler.armSchedule(next.hour, next.minute);
    final handoff = widget.handoff ?? SessionHandoff(scheduler: _scheduler);
    final session = await handoff.afterDismiss(away: _gate.awayActive);
    if (session && mounted) {
      developer.log('dismiss: opening session', name: 'WakeAlarmRing');
      await Navigator.of(context).pushReplacementNamed(kSessionRoute);
      return;
    }
    developer.log('dismiss: closing screen', name: 'WakeAlarmRing');
    await _scheduler.closeRingScreen();
  }

  @override
  Widget build(BuildContext context) => RingBody(
    gate: _gate,
    challenge: _challenge,
    controller: _input,
    status: _status,
    onSubmit: _submit,
  );
}
