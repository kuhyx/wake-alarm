import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/room_proof.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';

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
  RoomProof _proof = RoomProof(scheduler: AlarmScheduler());
  RoomProofSettings _settings = const RoomProofSettings();
  bool _nfcAvailable = false;
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
    _proof = RoomProof(scheduler: _scheduler);
    unawaited(_scheduler.beginStepCount());
    unawaited(_loadRoomProof());
    _startFlashTimerIfNeeded();
  }

  /// Loads the registered tag/QR and starts listening for NFC taps.
  Future<void> _loadRoomProof() async {
    final settings = await RoomProofSettings.load();
    final hasNfc = await _scheduler.hasNfc();
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _nfcAvailable = hasNfc;
      _proof = RoomProof(
        scheduler: _scheduler,
        registeredTagId: settings.nfcTagId,
      );
    });
    _scheduler.onNfcTag(_onNfcTag);
  }

  void _onNfcTag(String tagId) {
    final result = _proof.checkNfc(tagId);
    if (!mounted) return;
    setState(() {
      _inRoom = result.satisfied;
      _status = result.detail;
    });
  }

  /// Called by the QR scanner when a code is decoded.
  void onQrScanned(String payload) {
    final result = _proof.checkQr(payload, expected: _settings.qrPayload ?? '');
    if (!mounted) return;
    setState(() {
      _inRoom = result.satisfied;
      _status = result.detail;
    });
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
      _nfcAvailable && _settings.nfcTagId != null
          ? 'Go to the other room and tap the NFC tag.'
          : 'Go to the other room: scan the QR code, or walk '
                '${RoomProof.requiredSteps} steps.',
      textAlign: TextAlign.center,
      style: theme.textTheme.bodyLarge,
    ),
    const SizedBox(height: 16),
    // The steps fallback stays reachable even when NFC is registered: a
    // single failing mechanism at 06:00 must never make the alarm
    // undismissable.
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
