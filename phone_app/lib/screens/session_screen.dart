import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/main.dart';
import 'package:wake_alarm_sync/screens/session_body.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_publisher.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';
import 'package:wake_alarm_sync/services/weight_entry.dart';

/// How often the clocks advance and the countdown redraws.
const Duration kSessionTick = Duration(seconds: 1);

/// Every this many ticks the motion watch is read.
const int kMotionPollEvery = 5;

/// Logs to logcat in release too: `developer.log` is invisible there, and a
/// morning that went wrong on the phone is only ever debugged from logcat.
void sessionLog(String message) => debugPrint('WakeAlarmSession: $message');

/// The silent half hour after the ring: weigh in, shower, dress, sit down.
///
/// Shown in `AlarmActivity` in place of the ring screen, so NFC reader mode
/// and the kept-on screen carry over. Nothing here rings by itself; the
/// deadlines are AlarmManager alarms armed through [AlarmScheduler.armReRing]
/// and this widget merely keeps them pointed at the live leg. What it does
/// decide is the still-phone ring, which needs a live sensor.
class SessionScreen extends StatefulWidget {
  /// Creates the screen; every dependency is injectable for tests.
  const SessionScreen({
    super.key,
    this.scheduler,
    this.store,
    this.clock,
    this.publish,
  });

  /// Platform bridge; defaults to the real MethodChannel.
  final AlarmScheduler? scheduler;

  /// Session persistence; defaults to SharedPreferences.
  final SessionStore? store;

  /// Wall clock; injectable because the legs are minutes apart.
  final DateTime Function()? clock;

  /// Pushes the finished session; defaults to [SessionPublisher.publish].
  final Future<String> Function()? publish;

  @override
  State<SessionScreen> createState() => _SessionScreenState();
}

class _SessionScreenState extends State<SessionScreen> {
  late final AlarmScheduler _scheduler = widget.scheduler ?? AlarmScheduler();
  late final SessionStore _store = widget.store ?? SessionStore();
  late final DateTime Function() _now = widget.clock ?? DateTime.now;
  late final Future<String> Function() _publish =
      widget.publish ?? SessionPublisher().publish;

  final TextEditingController _input = TextEditingController();
  MorningSession? _session;
  SessionTagSettings _tags = const SessionTagSettings();
  double? _lastWeight;
  double? _confirming;
  Timer? _timer;
  int _ticks = 0;
  bool _finishing = false;
  String _status = '';

  @override
  void initState() {
    super.initState();
    unawaited(_init());
  }

  /// Loads the session the ring screen left, or starts one if reached cold.
  Future<void> _init() async {
    final tags = await SessionTagSettings.load();
    final now = _now();
    var session = await _store.loadCurrent();
    if (session == null) {
      session = SessionRules.start(
        now: now,
        tags: tags,
        nfcAvailable: await _scheduler.hasNfc(),
      );
      // Persist before anything can ring: a re-ring replaces this engine and
      // resumes from the store, so an unsaved session would restart at zero.
      await _store.save(session);
    }
    final last = await _store.lastWeightKg();
    await _scheduler.beginMotionWatch();
    await _scheduler.armReRing(session.nextDeadline());
    if (!mounted) return;
    setState(() {
      _tags = tags;
      _session = session;
      _lastWeight = last;
    });
    _scheduler.onNfcTag(_onTag);
    sessionLog(
      'started leg=${session.currentLeg?.name} re-rings=${session.reRings} '
      'deadline=${session.nextDeadline()}',
    );
    _timer = Timer.periodic(kSessionTick, (_) => unawaited(_onTick()));
    if (!session.isActive) await _finish();
  }

  Future<void> _onTag(String tagId) async {
    final session = _session;
    if (session == null) return;
    final slot = _tags.slotOf(tagId);
    final detail = slot == null ? 'Unknown tag' : session.onTag(slot, _now());
    sessionLog('tag=$tagId slot=$slot: $detail');
    await _commit(detail);
  }

  Future<void> _submitWeight() async {
    final session = _session;
    if (session == null) return;
    final check = checkWeight(
      _input.text,
      last: _lastWeight,
      confirming: _confirming,
    );
    if (!check.accepted) {
      _confirming = check.verdict == WeightVerdict.needsConfirm
          ? check.kg
          : null;
      setState(() => _status = check.detail);
      return;
    }
    _confirming = null;
    _input.clear();
    await _commit(session.enterWeight(check.kg!, _now()));
  }

  /// Persists, re-points the deadline, and ends the session if it is over.
  Future<void> _commit(String status) async {
    final session = _session!;
    await _store.save(session);
    await _scheduler.armReRing(session.nextDeadline());
    if (!mounted) return;
    setState(() => _status = status);
    if (!session.isActive) await _finish();
  }

  Future<void> _onTick() async {
    final session = _session;
    if (session == null || _finishing) return;
    final now = _now();
    final tick = session.tick(now);
    if (tick.changed) {
      // A bypass passes a leg, so the deadline moves with it.
      await _store.save(session);
      await _scheduler.armReRing(session.nextDeadline());
    }
    if (tick.ringReason != null) {
      await _ring(tick.ringReason!, now);
      return;
    }
    _ticks++;
    if (_ticks % kMotionPollEvery == 0) {
      final idle = await _scheduler.motionIdle();
      if (session.stillnessRingDue(idle)) {
        await _ring('still:${session.currentLeg!.name}', now);
        return;
      }
    }
    if (!mounted) return;
    setState(() {
      if (tick.note != null) _status = tick.note!;
    });
    if (!session.isActive) await _finish();
  }

  /// Rings now. The ring usually replaces this engine, so persist first.
  ///
  /// Then route to the ring screen anyway: `AlarmActivity` is
  /// `singleInstance`, and if the full-screen intent lands on the live
  /// instance instead of recreating it, nothing else would put the dismiss
  /// sequence in front of the sound.
  Future<void> _ring(String reason, DateTime now) async {
    final session = _session!..markReRing(reason, now);
    await _store.save(session);
    sessionLog('re-ring: $reason');
    _timer?.cancel();
    await _scheduler.ringNow();
    if (!mounted) return;
    await Navigator.of(context).pushReplacementNamed(kRingRoute);
  }

  /// Drops the deadline, archives, publishes, and closes the activity.
  ///
  /// Ordered so that a publish failure can never leave a re-ring armed.
  Future<void> _finish() async {
    if (_finishing) return;
    _finishing = true;
    _timer?.cancel();
    final session = _session!;
    await _scheduler.finishSession();
    await _store.archive(session);
    final message = await _publish();
    sessionLog(
      'finished ${session.outcome.name} re-rings=${session.reRings}: $message',
    );
    if (mounted) setState(() => _status = message);
    await _scheduler.closeRingScreen();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _scheduler.clearNfcListener();
    _input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final session = _session;
    if (session == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return SessionBody(
      session: session,
      now: _now(),
      controller: _input,
      status: _status,
      onSubmitWeight: () => unawaited(_submitWeight()),
    );
  }
}
