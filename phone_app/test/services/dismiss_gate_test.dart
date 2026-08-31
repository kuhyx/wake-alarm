import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';

/// Drives a fresh gate through tag 1 -> steps -> tag 2, onto challenges.
DismissGate _atChallenges() {
  final gate = DismissGate()
    ..passTagStage()
    ..passStepsStage()
    ..passTagStage();
  expect(gate.stage, DismissStage.challenges);
  return gate;
}

void main() {
  group('strict ordering', () {
    test('a fresh gate waits for tag 1', () {
      final gate = DismissGate();
      expect(gate.stage, DismissStage.tag1);
      expect(gate.expectedTagSlot, 0);
      expect(gate.isDone, isFalse);
    });

    test('steps before tag 1 do not advance anything', () {
      final gate = DismissGate();
      expect(gate.passStepsStage(), isFalse);
      expect(gate.stage, DismissStage.tag1);
    });

    test('the sequence runs tag 1 -> steps -> tag 2 -> challenges', () {
      final gate = DismissGate();
      expect(gate.passTagStage(), isTrue);
      expect(gate.stage, DismissStage.steps);
      expect(gate.expectedTagSlot, isNull, reason: 'no tag stage is live');
      expect(gate.passStepsStage(), isTrue);
      expect(gate.stage, DismissStage.tag2);
      expect(gate.expectedTagSlot, 1);
      expect(gate.passTagStage(), isTrue);
      expect(gate.stage, DismissStage.challenges);
    });

    test('a tag tapped during the steps stage does not advance it', () {
      final gate = DismissGate()..passTagStage();
      expect(gate.stage, DismissStage.steps);
      expect(gate.passTagStage(), isFalse);
      expect(gate.stage, DismissStage.steps, reason: 'steps still required');
    });
  });

  group('latching', () {
    test('a passed stage never reverts', () {
      // The bug this replaces: the old gate assigned the room-proof result
      // straight onto a bool, so a wrong tap after passing hid the challenge.
      final gate = _atChallenges();
      expect(gate.passTagStage(), isFalse);
      expect(gate.passStepsStage(), isFalse);
      expect(gate.stage, DismissStage.challenges);
    });

    test('finishing does not un-finish', () {
      final gate = _atChallenges();
      for (var i = 0; i < DismissGate.challengesNormal; i++) {
        gate.recordChallenge(correct: true);
      }
      expect(gate.isDone, isTrue);
      expect(gate.recordChallenge(correct: false), isFalse);
      expect(gate.isDone, isTrue);
    });
  });

  group('challenges', () {
    test('one correct answer is not enough; three are', () {
      final gate = _atChallenges()..recordChallenge(correct: true);
      expect(gate.isDone, isFalse);
      gate.recordChallenge(correct: true);
      expect(gate.isDone, isFalse);
      gate.recordChallenge(correct: true);
      expect(gate.isDone, isTrue);
    });

    test('a wrong answer does NOT reset the tally', () {
      final gate = _atChallenges()
        ..recordChallenge(correct: true)
        ..recordChallenge(correct: true)
        ..recordChallenge(correct: false);
      expect(gate.challengesPassed, 2, reason: 'cumulative, not consecutive');
      gate.recordChallenge(correct: true);
      expect(gate.isDone, isTrue);
    });

    test('answers before the challenge stage are ignored', () {
      final gate = DismissGate();
      expect(gate.recordChallenge(correct: true), isFalse);
      expect(gate.challengesPassed, 0);
    });
  });

  group('bypass', () {
    test('it drops the tags but NOT the walk', () {
      final gate = DismissGate();
      expect(gate.activateBypass(), isTrue);
      expect(gate.bypassActive, isTrue);
      expect(gate.stage, DismissStage.steps, reason: 'steps still required');
      expect(gate.challengesRequired, DismissGate.challengesBypass);
    });

    test('six answers are needed once bypassed, and five are not', () {
      final gate = DismissGate()
        ..activateBypass()
        ..passStepsStage();
      expect(gate.stage, DismissStage.challenges, reason: 'tag 2 is skipped');
      for (var i = 0; i < DismissGate.challengesBypass - 1; i++) {
        gate.recordChallenge(correct: true);
      }
      expect(gate.isDone, isFalse);
      gate.recordChallenge(correct: true);
      expect(gate.isDone, isTrue);
    });

    test('bypassing after tag 1 still requires the walk', () {
      final gate = DismissGate()
        ..passTagStage()
        ..activateBypass();
      expect(gate.stage, DismissStage.steps);
      gate.passStepsStage();
      expect(gate.stage, DismissStage.challenges);
    });

    test('bypassing at tag 2 keeps the already-banked steps', () {
      final gate = DismissGate()
        ..passTagStage()
        ..passStepsStage();
      expect(gate.stage, DismissStage.tag2);
      gate.activateBypass();
      expect(gate.stage, DismissStage.challenges);
    });

    test('it cannot fire once the challenges are live', () {
      // Raising 3 to 6 mid-answer would punish someone who did the walk.
      final gate = _atChallenges();
      expect(gate.activateBypass(), isFalse);
      expect(gate.challengesRequired, DismissGate.challengesNormal);
    });

    test('it is one-way and idempotent', () {
      final gate = DismissGate();
      expect(gate.activateBypass(), isTrue);
      expect(gate.activateBypass(), isFalse);
      expect(gate.challengesRequired, DismissGate.challengesBypass);
    });

    test('tags do nothing once bypassed', () {
      final gate = DismissGate()..activateBypass();
      expect(gate.expectedTagSlot, isNull);
      expect(gate.passTagStage(), isFalse);
      expect(gate.stage, DismissStage.steps);
    });
  });

  test('the bypass is strictly harder than the normal path', () {
    expect(
      DismissGate.challengesBypass,
      greaterThan(DismissGate.challengesNormal),
    );
  });

  group('away from home', () {
    test('skips the tags but keeps the normal challenge count', () {
      final gate = DismissGate()..activateAwayProfile();
      expect(gate.bypassActive, isTrue);
      expect(gate.challengesRequired, DismissGate.challengesNormal);
      expect(gate.stage, DismissStage.steps);
    });

    test('still requires the walk', () {
      final gate = DismissGate()..activateAwayProfile();
      expect(gate.stage, DismissStage.steps);
      expect(gate.passStepsStage(), isTrue);
      expect(gate.stage, DismissStage.challenges);
    });

    test('the five-minute bypass cannot raise an away morning to 6', () {
      // The ring screen's bypass timer fires unconditionally, and an away
      // morning is a two-minute walk plus three questions -- it crosses five
      // minutes routinely. If this ever returns true the user is punished
      // for travelling, and the only symptom is one wrong digit on screen.
      final gate = DismissGate()..activateAwayProfile();
      expect(gate.activateBypass(), isFalse);
      expect(gate.challengesRequired, DismissGate.challengesNormal);
    });

    test('a missing-tags bypass already at 6 is not lowered by away', () {
      final gate = DismissGate()..activateBypass();
      expect(gate.activateAwayProfile(), isFalse);
      expect(gate.challengesRequired, DismissGate.challengesBypass);
    });

    test('is idempotent', () {
      final gate = DismissGate()..activateAwayProfile();
      expect(gate.activateAwayProfile(), isFalse);
    });

    test('says away, not "tags unavailable", and only when it is', () {
      // Wording only -- a hotel is not a hardware fault. Must stay off the
      // latch, so it can never move the challenge count.
      expect(DismissGate().awayActive, isFalse);
      expect((DismissGate()..activateBypass()).awayActive, isFalse);
      final away = DismissGate()..activateAwayProfile();
      expect(away.awayActive, isTrue);
      expect(away.challengesRequired, DismissGate.challengesNormal);
    });

    test('a refused away skip does not claim to be away', () {
      final gate = DismissGate()..activateBypass();
      expect(gate.activateAwayProfile(), isFalse);
      expect(gate.awayActive, isFalse);
      expect(gate.challengesRequired, DismissGate.challengesBypass);
    });

    test('is refused once the challenges are live', () {
      final gate = DismissGate()
        ..passTagStage()
        ..passStepsStage()
        ..passTagStage();
      expect(gate.stage, DismissStage.challenges);
      expect(gate.activateAwayProfile(), isFalse);
      expect(gate.challengesRequired, DismissGate.challengesNormal);
    });

    test('past tag 2 the banked steps are not asked for again', () {
      final gate = DismissGate()..passTagStage();
      expect(gate.passStepsStage(), isTrue);
      expect(gate.stage, DismissStage.tag2);
      expect(gate.activateAwayProfile(), isTrue);
      expect(gate.stage, DismissStage.challenges);
      expect(gate.challengesRequired, DismissGate.challengesNormal);
    });
  });
}
