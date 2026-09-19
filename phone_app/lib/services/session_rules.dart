import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';
import 'package:wake_alarm_sync/services/weight_entry.dart';

/// What a clock tick decided; the driver acts on it, the session records it.
class SessionTick {
  /// Creates a tick result.
  const SessionTick({this.changed = false, this.ringReason, this.note});

  /// Whether the session must be re-persisted.
  final bool changed;

  /// Why to ring right now, or null.
  ///
  /// Set only for a deadline the native alarm should already have fired —
  /// calling the ring twice is harmless, missing it is not.
  final String? ringReason;

  /// Something to show, or null.
  final String? note;
}

/// Grace after a deadline before Dart rings it itself, in case the
/// AlarmManager alarm did not.
const Duration _deadlineGrace = Duration(seconds: 20);

/// Starts and advances a [MorningSession]; the rules half of the record.
extension SessionRules on MorningSession {
  /// Begins today's session, skipping every leg whose tag does not exist.
  ///
  /// With NFC off or no session tags registered this is a weigh-in and
  /// nothing else — the feature must be usable before it is configured, and
  /// a leg that can never pass must never be required.
  static MorningSession start({
    required DateTime now,
    required SessionTagSettings tags,
    required bool nfcAvailable,
  }) {
    final session = MorningSession(
      date: dateKey(now),
      startedAt: now,
      updatedAt: now,
      bathroomTagRequired:
          nfcAvailable && tags.tagAt(SessionTagSlot.bathroom) != null,
    );
    for (final leg in SessionLeg.values) {
      if (leg == SessionLeg.bathroomIn) continue;
      if (!nfcAvailable || tags.tagAt(leg.slot) == null) {
        session.passedAt[leg] = now;
        session.passedHow[leg] = LegPass.skipped;
      }
    }
    return session;
  }

  /// `yyyy-mm-dd` of [now], local.
  static String dateKey(DateTime now) => now.toIso8601String().substring(0, 10);

  /// Records the check-in: a typed, already-validated weight and the
  /// energy tap.
  ///
  /// The weight is pending until the bathroom tag confirms it; without a
  /// bathroom tag it is the whole first leg. The energy rating is not proof
  /// of anything — it is the one number worth a tap while standing there.
  String enterCheckIn(double kg, int energyLevel, DateTime now) {
    if (currentLeg != SessionLeg.bathroomIn) return 'Already weighed in';
    if (energyLevel < minEnergy || energyLevel > maxEnergy) {
      return 'Pick your energy ($minEnergy-$maxEnergy)';
    }
    updatedAt = now;
    energy = energyLevel;
    if (!bathroomTagRequired) {
      weightKg = kg;
      _pass(SessionLeg.bathroomIn, now, LegPass.tag);
      return '$kg kg noted';
    }
    pendingWeightKg = kg;
    pendingWeightAt = now;
    return '$kg kg — now tap the bathroom tag within '
        '${confirmWindow.inMinutes} min';
  }

  /// Applies a tag tap for [slot]; only the live leg's room advances.
  String onTag(SessionTagSlot slot, DateTime now) {
    final leg = currentLeg;
    if (leg == null) return 'Session finished';
    if (slot != leg.slot) return 'Not the ${leg.slot.name} tag';
    switch (leg) {
      case SessionLeg.bathroomIn:
        final typedAt = pendingWeightAt;
        final kg = pendingWeightKg;
        if (kg == null || typedAt == null) {
          return 'Weigh in first, then tap the bathroom tag';
        }
        if (now.difference(typedAt) > confirmWindow) {
          _clearPendingWeight(now);
          return 'That weight expired — type it again at the scale';
        }
        weightKg = kg;
        _clearPendingWeight(now);
      case SessionLeg.showerDone:
        final soonest = earliest(leg)!;
        if (now.isBefore(soonest)) {
          final left = soonest.difference(now);
          return 'Too early — shower first (${left.inMinutes + 1} min left)';
        }
      case SessionLeg.dressed || SessionLeg.atDesk:
        break;
    }
    _pass(leg, now, LegPass.tag);
    return outcome == SessionOutcome.completed
        ? 'Session complete — have a good day'
        : 'Done: ${leg.label}';
  }

  /// Advances the clocks to [now].
  SessionTick tick(DateTime now) {
    final leg = currentLeg;
    if (!isActive || leg == null) return const SessionTick();
    final typedAt = pendingWeightAt;
    if (typedAt != null && now.difference(typedAt) > confirmWindow) {
      _clearPendingWeight(now);
      return const SessionTick(
        changed: true,
        note: 'That weight expired — type it again at the scale',
      );
    }
    if (now.isBefore(deadline(leg))) return const SessionTick();
    if (deadlineRung.contains(leg)) {
      if (now.isBefore(bypassAt(leg))) return const SessionTick();
      // The dead-tag hatch: the re-ring has been paid, the grace has run.
      _pass(leg, now, LegPass.bypassed);
      return SessionTick(changed: true, note: 'Skipped: ${leg.label}');
    }
    if (!canReRing) {
      outcome = SessionOutcome.failed;
      updatedAt = now;
      return const SessionTick(
        changed: true,
        note: 'Missed with no re-rings left — session failed',
      );
    }
    if (now.isBefore(deadline(leg).add(_deadlineGrace))) {
      return const SessionTick();
    }
    return SessionTick(ringReason: 'deadline:${leg.name}');
  }

  /// Names the re-ring the driver is about to trigger.
  void markReRing(String reason, DateTime now) {
    pendingReRingReason = reason;
    updatedAt = now;
  }

  /// Records that a re-ring was dismissed; the session resumes here.
  ///
  /// A leg whose deadline has already passed is marked as rung whatever the
  /// reason: its native alarm fired into the ring that was already sounding,
  /// so ringing it again on resume would be a second bill for one miss.
  void recordReRing(DateTime now) {
    final leg = currentLeg;
    reRings++;
    reRingReasons.add(pendingReRingReason ?? 'deadline:${leg?.name ?? 'none'}');
    pendingReRingReason = null;
    if (leg != null && !now.isBefore(deadline(leg))) deadlineRung.add(leg);
    updatedAt = now;
  }

  /// The instant to arm natively for the live leg, or null when nothing
  /// should ring: no legs left, the leg already re-rang, or no re-rings left.
  DateTime? nextDeadline() {
    final leg = currentLeg;
    if (!isActive || leg == null) return null;
    if (deadlineRung.contains(leg) || !canReRing) return null;
    return deadline(leg);
  }

  void _pass(SessionLeg leg, DateTime now, LegPass how) {
    passedAt[leg] = now;
    passedHow[leg] = how;
    updatedAt = now;
    if (currentLeg == null) outcome = SessionOutcome.completed;
  }

  void _clearPendingWeight(DateTime now) {
    pendingWeightKg = null;
    pendingWeightAt = null;
    updatedAt = now;
  }
}
