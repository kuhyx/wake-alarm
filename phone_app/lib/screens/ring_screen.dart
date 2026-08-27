import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/room_proof.dart';

/// The dismiss screen shown over the lockscreen while the alarm rings.
///
/// Two gates, in order: prove you are in the other room, then solve a
/// challenge. Only then does the sound stop.
class RingScreen extends StatefulWidget {
  /// Creates the ring screen; both dependencies are injectable for tests.
  const RingScreen({super.key, this.scheduler, this.generator});

  /// Platform bridge; defaults to the real MethodChannel.
  final AlarmScheduler? scheduler;

  /// Challenge source; defaults to a secure-random generator.
  final ChallengeGenerator? generator;

  @override
  State<RingScreen> createState() => _RingScreenState();
}

class _RingScreenState extends State<RingScreen> {
  late final AlarmScheduler _scheduler = widget.scheduler ?? AlarmScheduler();
  late final ChallengeGenerator _generator =
      widget.generator ?? ChallengeGenerator();
  late final RoomProof _proof = RoomProof(scheduler: _scheduler);
  late Challenge _challenge = _generator.next();

  final TextEditingController _input = TextEditingController();
  final Stopwatch _elapsed = Stopwatch()..start();

  /// Whether the room proof has been satisfied; the challenge is gated on it.
  bool _inRoom = false;
  String _status = '';

  /// Hidden after [kDismissFlashSeconds] for the flash challenge only.
  bool _codeVisible = true;
  Timer? _flashTimer;

  @override
  void initState() {
    super.initState();
    unawaited(_scheduler.beginStepCount());
    _startFlashTimerIfNeeded();
  }

  @override
  void dispose() {
    _flashTimer?.cancel();
    _input.dispose();
    _elapsed.stop();
    super.dispose();
  }

  void _startFlashTimerIfNeeded() {
    if (_challenge.kind != ChallengeKind.flash) return;
    _flashTimer?.cancel();
    _flashTimer = Timer(const Duration(seconds: kDismissFlashSeconds), () {
      if (mounted) setState(() => _codeVisible = false);
    });
  }

  Future<void> _trySteps() async {
    final result = await _proof.checkSteps(_elapsed.elapsed);
    if (!mounted) return;
    setState(() {
      _inRoom = result.satisfied;
      _status = result.detail;
    });
  }

  void _submit() {
    if (!_challenge.accepts(_input.text)) {
      setState(() {
        _status = 'Wrong — here is another one';
        _challenge = _generator.next();
        _codeVisible = true;
        _input.clear();
      });
      _startFlashTimerIfNeeded();
      return;
    }
    unawaited(_scheduler.dismiss());
    setState(() => _status = 'Dismissed');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
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
                if (!_inRoom) ..._roomGate(theme) else ..._challengeGate(theme),
                const SizedBox(height: 16),
                Text(_status, style: theme.textTheme.bodyMedium),
              ],
            ),
          ),
        ),
      ),
    );
  }

  List<Widget> _roomGate(ThemeData theme) => <Widget>[
    Text(
      'Go to the other room: tap the NFC tag, scan the QR code, '
      'or walk ${RoomProof.requiredSteps} steps.',
      textAlign: TextAlign.center,
      style: theme.textTheme.bodyLarge,
    ),
    const SizedBox(height: 16),
    FilledButton(onPressed: _trySteps, child: const Text('Check steps')),
  ];

  List<Widget> _challengeGate(ThemeData theme) => <Widget>[
    Text(_challenge.hint, style: theme.textTheme.bodyLarge),
    const SizedBox(height: 12),
    Text(
      _codeVisible ? _challenge.display : '••••••',
      textAlign: TextAlign.center,
      style: theme.textTheme.displaySmall,
    ),
    const SizedBox(height: 16),
    TextField(
      controller: _input,
      autofocus: true,
      textCapitalization: TextCapitalization.characters,
      decoration: const InputDecoration(labelText: 'Answer'),
      onSubmitted: (_) => _submit(),
    ),
    const SizedBox(height: 16),
    FilledButton(onPressed: _submit, child: const Text('Dismiss')),
  ];
}
