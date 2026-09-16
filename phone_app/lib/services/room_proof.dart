import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';

/// Which mechanism satisfied a stage of the separate-room requirement.
enum RoomProofKind {
  /// Tapped the registered NFC tag for the stage that was live.
  nfc,

  /// Walked far enough, for long enough, since the alarm started.
  steps,
}

/// Result of a room-proof attempt.
class RoomProofResult {
  /// Creates a result; [kind] is null when nothing has satisfied yet.
  const RoomProofResult({required this.satisfied, this.kind, this.detail = ''});

  /// Whether this particular check passed.
  final bool satisfied;

  /// Which mechanism satisfied it, or null if none did.
  final RoomProofKind? kind;

  /// Human-readable reason, shown on the ring screen.
  final String detail;
}

/// The individual checks behind the dismiss sequence.
///
/// **Every check is required, in order** — see `DismissGate`, which owns the
/// sequencing. This class only answers "did this one thing pass right now".
///
/// Steps deliberately require elapsed time as well as a count: the phone is
/// stationary while you walk *to* it, so a bare step count can be faked by
/// shaking it in bed. The pair is unchanged from when steps were a fallback.
class RoomProof {
  /// Creates a room-proof checker over [scheduler]'s platform channel.
  RoomProof({
    required this.scheduler,
    this.settings = const RoomProofSettings(),
  });

  /// Platform bridge used to read the step counter.
  final AlarmScheduler scheduler;

  /// The registered tags, one per sequence stage.
  final RoomProofSettings settings;

  /// Steps required, counted since the alarm started ringing.
  static const int requiredSteps = 25;

  /// Elapsed time also required **under bypass**, so shaking the phone
  /// cannot pass when no tag proved the walk.
  ///
  /// Not applied on the normal path since 2026-09-16: tag 1 has already
  /// banked the steps by the time this stage is live, so the floor was two
  /// minutes of ringing that nothing the user did could shorten.
  static const Duration requiredElapsed = Duration(minutes: 2);

  /// Whether [tagId] is the tag registered for [slot].
  ///
  /// A tag registered for a *different* slot fails here: tapping tag 2 while
  /// stage 1 is live must not advance anything, or the two locations collapse
  /// into one.
  RoomProofResult checkNfc(String tagId, {required int slot}) {
    final expected = settings.tagAt(slot);
    if (expected == null) {
      return RoomProofResult(
        satisfied: false,
        detail: 'No tag ${slot + 1} registered in Settings',
      );
    }
    if (tagId != expected) {
      return RoomProofResult(satisfied: false, detail: 'Not tag ${slot + 1}');
    }
    return RoomProofResult(
      satisfied: true,
      kind: RoomProofKind.nfc,
      detail: 'Tag ${slot + 1} matched',
    );
  }

  /// Enough steps, and — when [floor] is set — enough elapsed time too.
  ///
  /// [elapsed] is passed in rather than measured here so the ring screen
  /// owns the single clock. [floor] is the bypass profile's anti-shake
  /// guard; with a tag stage passed the walk is already proven.
  Future<RoomProofResult> checkSteps(
    Duration elapsed, {
    bool floor = true,
  }) async {
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
    if (floor && elapsed < requiredElapsed) {
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
