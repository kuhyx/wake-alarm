import 'package:wake_alarm_sync/services/session_tag_settings.dart';

/// The legs of the morning session, in the order they must be walked.
enum SessionLeg {
  /// Weigh in, then tap the bathroom tag within two minutes.
  bathroomIn,

  /// Tap the bathroom tag again, at least eight minutes later: the shower.
  showerDone,

  /// Tap the wardrobe tag.
  dressed,

  /// Tap the desk tag. The day has started.
  atDesk,
}

/// Which room's tag a leg expects.
extension SessionLegSlot on SessionLeg {
  /// The tag slot for this leg.
  SessionTagSlot get slot => switch (this) {
    SessionLeg.bathroomIn || SessionLeg.showerDone => SessionTagSlot.bathroom,
    SessionLeg.dressed => SessionTagSlot.wardrobe,
    SessionLeg.atDesk => SessionTagSlot.desk,
  };

  /// What the checklist calls this leg.
  String get label => switch (this) {
    SessionLeg.bathroomIn => 'Tap the bathroom tag',
    SessionLeg.showerDone => 'Shower, then tap the bathroom tag again',
    SessionLeg.dressed => 'Get dressed — tap the wardrobe tag',
    SessionLeg.atDesk => 'Sit down — tap the desk tag',
  };
}

/// How a leg came to be passed.
enum LegPass {
  /// The right tag, at the right time.
  tag,

  /// No tag registered for it, so it was never required.
  skipped,

  /// Never satisfied; passed by the clock after a missed deadline.
  bypassed,
}

/// Where the session stands.
enum SessionOutcome {
  /// Legs remain.
  active,

  /// Every leg passed.
  completed,

  /// A deadline was missed with no re-rings left.
  failed,
}

/// One morning's session: the state, the clocks, and the JSON that persists
/// them.
///
/// **Persisted after every change and driven by wall-clock instants**, never
/// Dart timers: the session screen can be killed, paused or rebooted away,
/// and the only thing that reliably comes back is what was written. The
/// rules that mutate this live in `session_rules.dart`; this file is the
/// record.
///
/// Legs latch like the ring's stages: a passed leg never reverts. The one
/// thing that is not a leg is the typed weight, which stays *pending* until
/// the bathroom tag confirms it — that is the walk-to-the-scale proof.
class MorningSession {
  /// Creates a session from persisted or freshly-started state.
  MorningSession({
    required this.date,
    required this.startedAt,
    required this.updatedAt,
    this.bathroomTagRequired = true,
    Map<SessionLeg, DateTime>? passedAt,
    Map<SessionLeg, LegPass>? passedHow,
    Set<SessionLeg>? deadlineRung,
    this.weightKg,
    this.pendingWeightKg,
    this.pendingWeightAt,
    this.reRings = 0,
    List<String>? reRingReasons,
    this.pendingReRingReason,
    this.outcome = SessionOutcome.active,
  }) : passedAt = passedAt ?? <SessionLeg, DateTime>{},
       passedHow = passedHow ?? <SessionLeg, LegPass>{},
       deadlineRung = deadlineRung ?? <SessionLeg>{},
       reRingReasons = reRingReasons ?? <String>[];

  /// Window each leg gets from the moment the previous one passed.
  static const Duration legWindow = Duration(minutes: 10);

  /// The shower cannot be over sooner than this after entering the bathroom.
  static const Duration showerMin = Duration(minutes: 8);

  /// The shower leg's own window; [legWindow] composed with [showerMin]
  /// would leave a two-minute target, hit wet, with the phone on a shelf.
  static const Duration showerWindow = Duration(minutes: 18);

  /// How long after a missed deadline an unsatisfiable leg passes itself.
  ///
  /// The dead-tag hatch. The deadline has already re-rung by then, so a
  /// missing tag costs one full dismiss sequence and five more minutes on
  /// your feet — never a silent skip.
  static const Duration bypassGrace = Duration(minutes: 5);

  /// Re-rings per morning before the session gives up.
  static const int maxReRings = 3;

  /// The session's calendar day, `yyyy-mm-dd` local.
  final String date;

  /// When the ring was dismissed and the session began.
  final DateTime startedAt;

  /// Whether a bathroom tag exists to confirm the weigh-in.
  ///
  /// Without one the typed weight passes [SessionLeg.bathroomIn] by itself;
  /// there is nothing to walk to.
  final bool bathroomTagRequired;

  /// When each passed leg passed.
  final Map<SessionLeg, DateTime> passedAt;

  /// How each passed leg passed.
  final Map<SessionLeg, LegPass> passedHow;

  /// Legs whose deadline already re-rang; each leg gets one.
  final Set<SessionLeg> deadlineRung;

  /// The confirmed weigh-in, kg.
  double? weightKg;

  /// A typed weight the bathroom tag has not confirmed yet.
  double? pendingWeightKg;

  /// When [pendingWeightKg] was typed.
  DateTime? pendingWeightAt;

  /// Re-rings dismissed so far this session.
  int reRings;

  /// Why each re-ring happened, e.g. `deadline:atDesk`.
  final List<String> reRingReasons;

  /// Set by the driver before it rings, so the dismiss can name the reason.
  String? pendingReRingReason;

  /// Where the session stands.
  SessionOutcome outcome;

  /// Last change, for the cross-device merge.
  DateTime updatedAt;

  /// The leg awaiting satisfaction, or null when none remains.
  SessionLeg? get currentLeg {
    for (final leg in SessionLeg.values) {
      if (!passedAt.containsKey(leg)) return leg;
    }
    return null;
  }

  /// When [leg]'s clock started: the previous leg's pass, or the start.
  DateTime legStart(SessionLeg leg) {
    if (leg.index == 0) return startedAt;
    return passedAt[SessionLeg.values[leg.index - 1]] ?? startedAt;
  }

  /// Before this instant [leg] cannot pass; only the shower has one.
  DateTime? earliest(SessionLeg leg) =>
      leg == SessionLeg.showerDone ? legStart(leg).add(showerMin) : null;

  /// The instant at which [leg] re-rings if still unsatisfied.
  DateTime deadline(SessionLeg leg) => legStart(
    leg,
  ).add(leg == SessionLeg.showerDone ? showerWindow : legWindow);

  /// The instant at which an already-re-rung [leg] passes itself.
  DateTime bypassAt(SessionLeg leg) => deadline(leg).add(bypassGrace);

  /// Whether another re-ring is allowed.
  bool get canReRing => reRings < maxReRings;

  /// Whether this session still needs driving.
  bool get isActive => outcome == SessionOutcome.active;
}
