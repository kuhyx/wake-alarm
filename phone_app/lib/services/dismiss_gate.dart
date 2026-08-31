/// The stages of the dismiss sequence, in the order they must be satisfied.
enum DismissStage {
  /// Tap the first registered tag.
  tag1,

  /// Walk far enough, for long enough.
  steps,

  /// Tap the second registered tag, somewhere else.
  tag2,

  /// Answer challenges until the required count is reached.
  challenges,

  /// Everything satisfied; the ring may stop.
  done,
}

/// The dismiss sequence: tag 1 -> steps -> tag 2 -> challenges.
///
/// **Strictly ordered and latched.** Every stage is required and each one,
/// once passed, can never revert — an unknown or out-of-order tag is simply
/// ignored. The previous gate was an OR that reverted on a wrong tap, so a
/// mistimed tag could send a half-awake user back to the start.
///
/// This owns sequencing only. Whether a given tag or step count actually
/// passes is `RoomProof`'s job, and generating questions is
/// `ChallengeGenerator`'s.
class DismissGate {
  /// Creates a gate at the first stage.
  DismissGate();

  /// How long the alarm may ring before NFC stops being required.
  ///
  /// The escape hatch for a dead tag, an NFC radio that will not read, or a
  /// tag that has fallen off the wall. Without it a hardware failure at 06:00
  /// leaves an alarm that literally cannot be switched off.
  static const Duration bypassAfter = Duration(minutes: 5);

  /// Challenges required on the normal path.
  static const int challengesNormal = 3;

  /// Challenges required once the NFC stages have been bypassed.
  ///
  /// Higher than [challengesNormal] so skipping the walk is never the cheap
  /// option, even though it is always an available one.
  static const int challengesBypass = 6;

  DismissStage _stage = DismissStage.tag1;
  int _challengesPassed = 0;
  int _challengesRequired = challengesNormal;
  bool _bypassed = false;
  bool _away = false;

  /// The stage currently awaiting satisfaction.
  DismissStage get stage => _stage;

  /// Challenges answered correctly so far.
  int get challengesPassed => _challengesPassed;

  /// Challenges needed in total; rises to [challengesBypass] under bypass.
  int get challengesRequired => _challengesRequired;

  /// Whether the NFC stages have been skipped.
  bool get bypassActive => _bypassed;

  /// Whether they were skipped because the phone is away from home.
  ///
  /// Purely for wording: "tags unavailable" reads as a hardware fault, which
  /// is the wrong thing to tell someone in a hotel. Kept off the latch so it
  /// cannot affect [challengesRequired] or the stage arithmetic.
  bool get awayActive => _away;

  /// Whether the alarm may now be dismissed.
  bool get isDone => _stage == DismissStage.done;

  /// Whether a tag tap could advance anything right now.
  bool get awaitingTag =>
      _stage == DismissStage.tag1 || _stage == DismissStage.tag2;

  /// Which registered tag slot the live stage expects, or null if none does.
  ///
  /// The ring screen passes this to `RoomProof.checkNfc` so that tapping the
  /// *other* registered tag fails: two locations must stay two locations.
  int? get expectedTagSlot => switch (_stage) {
    DismissStage.tag1 => 0,
    DismissStage.tag2 => 1,
    _ => null,
  };

  /// Records that the tag for the live stage was tapped.
  ///
  /// Ignored unless a tag stage is live, so a tap arriving during the steps
  /// stage or after bypass changes nothing.
  bool passTagStage() {
    if (_stage == DismissStage.tag1) {
      _stage = DismissStage.steps;
      return true;
    }
    if (_stage == DismissStage.tag2) {
      _stage = DismissStage.challenges;
      return true;
    }
    return false;
  }

  /// Records that the step requirement was met.
  ///
  /// Ignored unless the steps stage is live: banking steps early must not
  /// carry over, or walking to tag 1 would satisfy the walk by itself.
  bool passStepsStage() {
    if (_stage != DismissStage.steps) return false;
    _stage = _bypassed ? DismissStage.challenges : DismissStage.tag2;
    return true;
  }

  /// Records a challenge answer; only a correct one counts.
  ///
  /// A wrong answer costs the attempt and nothing else — the count never
  /// decreases, so guessing cannot dig a hole a half-asleep user can't climb.
  bool recordChallenge({required bool correct}) {
    if (_stage != DismissStage.challenges) return false;
    if (!correct) return false;
    _challengesPassed++;
    if (_challengesPassed >= _challengesRequired) {
      _stage = DismissStage.done;
    }
    return true;
  }

  /// Drops the NFC requirement, raising the challenge count instead.
  ///
  /// The escape hatch for tags that cannot be read: a dead tag, an NFC radio
  /// that will not poll, a tag that fell off the wall. The count rises so
  /// skipping the walk is never the cheap option.
  ///
  /// Refused once [activateAwayProfile] has fired: away from home the tags
  /// are already gone, so the only remaining effect would be the punitive
  /// 3 -> 6, which is exactly what the away morning must not get. That guard
  /// is load-bearing, not defensive — the ring screen's [bypassAfter] timer
  /// fires unconditionally, and an away morning is a two-minute walk plus
  /// three questions, which crosses five minutes routinely.
  bool activateBypass() => _skipTags(challengesBypass);

  /// Skips the tag stages because the tags are somewhere else entirely.
  ///
  /// Being away from home is not cheating, so unlike [activateBypass] the
  /// count stays at [challengesNormal]. **The walk is still required**: the
  /// tags are what cannot be reached in a hotel, not the standing up.
  bool activateAwayProfile() {
    final skipped = _skipTags(challengesNormal);
    if (skipped) _away = true;
    return skipped;
  }

  /// Skips the two tag stages and fixes the challenge count at [required].
  ///
  /// **Only the two tag stages are skipped — the walk still counts.** Jumping
  /// straight to the challenges would let someone lie in bed for
  /// [bypassAfter] and then answer questions without ever standing up, which
  /// is a weaker gate than the one this change replaced.
  ///
  /// One-way and idempotent, so whichever reason arrives first wins and no
  /// later one can raise the count behind the user's back. Deliberately
  /// refused once the challenge stage is live: the user has already done the
  /// walk by then, and raising 3 to 6 mid-answer would punish them for being
  /// slow at arithmetic.
  bool _skipTags(int required) {
    if (_bypassed) return false;
    if (_stage == DismissStage.challenges || _stage == DismissStage.done) {
      return false;
    }
    _bypassed = true;
    _challengesRequired = required;
    // Past tag 2 the steps are already banked; otherwise fall back to them.
    _stage = _stage == DismissStage.tag2
        ? DismissStage.challenges
        : DismissStage.steps;
    return true;
  }
}
