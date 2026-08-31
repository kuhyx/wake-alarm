import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';
import 'package:wake_alarm_sync/services/home_presence.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';

/// Why, if at all, the ring screen should skip the two NFC tag stages.
enum RingSkip {
  /// The strict sequence applies: tag 1, walk, tag 2, challenges.
  none,

  /// The phone is not at its registered home, so the tags are unreachable.
  ///
  /// The challenge count stays at [DismissGate.challengesNormal].
  away,

  /// NFC is off, or fewer than two distinct tags are registered.
  ///
  /// The challenge count rises to [DismissGate.challengesBypass].
  noTags,
}

/// What the ring screen learned before it could decide anything.
class RingStartup {
  /// Creates a startup decision.
  const RingStartup({
    required this.settings,
    required this.skip,
    required this.status,
  });

  /// The registered tags, for `RoomProof`.
  final RoomProofSettings settings;

  /// Which skip, if any, to apply to the gate.
  final RingSkip skip;

  /// A line for the ring screen; empty when the strict sequence applies.
  final String status;
}

/// Resolves what the ring screen should do, in one strictly ordered pass.
///
/// **Presence is resolved first, and that ordering is the point.** Both skips
/// latch one-way, so whichever fires first fixes the challenge count. If the
/// missing-tags check ran first it would set 6, the away verdict arriving a
/// moment later could not lower it, and every away morning with NFC off would
/// silently get the punitive count.
///
/// Sequential rather than concurrent for the same reason `HomeScreen`'s
/// bootstrap is: the later steps read what the earlier ones decide, and the
/// last time these ran in parallel the result was a value captured before it
/// was ever assigned.
Future<RingStartup> resolveRingStartup({
  required AlarmScheduler scheduler,
  required HomePresence presence,
}) async {
  final verdict = await presence.resolve();
  final settings = await RoomProofSettings.load();
  final hasNfc = await scheduler.hasNfc();
  if (verdict.skipsTags) {
    return RingStartup(
      settings: settings,
      skip: RingSkip.away,
      status: 'Away from home (${verdict.detail}) — tags skipped.',
    );
  }
  // Nothing to wait for: without NFC or without two distinct tags the tag
  // stages can never be satisfied, so making the user sit through the full
  // timer would be pure punishment for a config problem.
  if (!hasNfc || !settings.isComplete) {
    return RingStartup(
      settings: settings,
      skip: RingSkip.noTags,
      status: hasNfc
          ? 'Register two NFC tags in Settings.'
          : 'NFC is off or unavailable.',
    );
  }
  return RingStartup(
    settings: settings,
    skip: RingSkip.none,
    status: '',
  );
}
