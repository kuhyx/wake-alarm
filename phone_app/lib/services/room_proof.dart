import 'package:wake_alarm_sync/services/alarm_scheduler.dart';

/// Which mechanism satisfied the separate-room requirement.
enum RoomProofKind {
  /// Tapped the registered NFC tag in the other room.
  nfc,

  /// Scanned the printed QR code in the other room.
  qr,

  /// Walked far enough, for long enough, since the alarm started.
  steps,
}

/// Result of a room-proof attempt.
class RoomProofResult {
  /// Creates a result; [kind] is null when nothing has satisfied yet.
  const RoomProofResult({required this.satisfied, this.kind, this.detail = ''});

  /// Whether the user has proven they are in the other room.
  final bool satisfied;

  /// Which mechanism satisfied it, or null if none did.
  final RoomProofKind? kind;

  /// Human-readable reason, shown on the ring screen.
  final String detail;
}

/// Proof that the user physically walked to another room before dismissing.
///
/// **Any one of NFC or QR satisfies.** Steps alone deliberately does NOT: the
/// phone is stationary in the other room while you walk *to* it, so steps only
/// accrue after pickup and can be faked by shaking it in bed. Steps are only
/// accepted together with elapsed time, as the fallback for when both other
/// mechanisms fail — a single failing mechanism at 06:00 must never make the
/// alarm undismissable.
class RoomProof {
  /// Creates a room-proof checker over [scheduler]'s platform channel.
  RoomProof({required this.scheduler, this._registeredTagId});

  /// Platform bridge used to read the step counter.
  final AlarmScheduler scheduler;
  final String? _registeredTagId;

  /// Steps required by the fallback, counted since the alarm started ringing.
  static const int requiredSteps = 25;

  /// Elapsed time the fallback also requires, so shaking the phone cannot pass.
  static const Duration requiredElapsed = Duration(minutes: 2);

  /// Whether [tagId] is the tag registered in Settings.
  ///
  /// Registering no tag means NFC cannot satisfy the proof — it does not mean
  /// every tag passes.
  RoomProofResult checkNfc(String tagId) {
    final registered = _registeredTagId;
    if (registered == null || registered.isEmpty) {
      return const RoomProofResult(
        satisfied: false,
        detail: 'No NFC tag registered in Settings',
      );
    }
    if (tagId != registered) {
      return const RoomProofResult(satisfied: false, detail: 'Wrong NFC tag');
    }
    return const RoomProofResult(
      satisfied: true,
      kind: RoomProofKind.nfc,
      detail: 'NFC tag matched',
    );
  }

  /// Whether [payload] is the expected printed QR code.
  ///
  /// A printed code is photographable, which is exactly why it is one of two
  /// accepted proofs rather than the only one.
  RoomProofResult checkQr(String payload, {required String expected}) {
    if (expected.isEmpty || payload != expected) {
      return const RoomProofResult(satisfied: false, detail: 'Wrong QR code');
    }
    return const RoomProofResult(
      satisfied: true,
      kind: RoomProofKind.qr,
      detail: 'QR code matched',
    );
  }

  /// The fallback: enough steps AND enough elapsed time since the ring started.
  ///
  /// Both are required together. [elapsed] is passed in rather than measured
  /// here so the ring screen owns the single clock.
  Future<RoomProofResult> checkSteps(Duration elapsed) async {
    final steps = await scheduler.stepsSinceRingStart();
    if (steps < 0) {
      return const RoomProofResult(
        satisfied: false,
        detail: 'Step sensor unavailable',
      );
    }
    if (steps < requiredSteps) {
      return RoomProofResult(
        satisfied: false,
        detail: '$steps/$requiredSteps steps',
      );
    }
    if (elapsed < requiredElapsed) {
      final left = requiredElapsed - elapsed;
      return RoomProofResult(
        satisfied: false,
        detail: 'Keep moving for ${left.inSeconds}s more',
      );
    }
    return const RoomProofResult(
      satisfied: true,
      kind: RoomProofKind.steps,
      detail: 'Walked far enough, long enough',
    );
  }
}
