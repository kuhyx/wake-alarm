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

  /// The stage currently awaiting satisfaction.
  DismissStage get stage => _stage;

  /// Challenges answered correctly so far.
  int get challengesPassed => _challengesPassed;

  /// Challenges needed in total; rises to [challengesBypass] under bypass.
  int get challengesRequired => _challengesRequired;

  /// Whether the NFC stages have been skipped.
  bool get bypassActive => _bypassed;

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
  /// **Only the two tag stages are skipped — the walk still counts.** Jumping
  /// straight to the challenges would let someone lie in bed for
  /// [bypassAfter] and then answer questions without ever standing up, which
  /// is a weaker gate than the one this change replaced.
  ///
  /// One-way and idempotent. Deliberately refused once the challenge stage is
  /// live: the user has already done the walk by then, and raising 3 to 6
  /// mid-answer would punish them for being slow at arithmetic.
  bool activateBypass() {
    if (_bypassed) return false;
    if (_stage == DismissStage.challenges || _stage == DismissStage.done) {
      return false;
    }
    _bypassed = true;
    _challengesRequired = challengesBypass;
    // Past tag 2 the steps are already banked; otherwise fall back to them.
    _stage = _stage == DismissStage.tag2
        ? DismissStage.challenges
        : DismissStage.steps;
    return true;
  }
}
