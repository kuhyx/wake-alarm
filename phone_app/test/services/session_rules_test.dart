import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_json.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

final DateTime t0 = DateTime(2026, 9, 17, 8, 5);
const SessionTagSettings allTags = SessionTagSettings(
  tagIds: <String>['bath', 'ward', 'desk'],
);

MorningSession fresh({SessionTagSettings tags = allTags, bool nfc = true}) =>
    SessionRules.start(now: t0, tags: tags, nfcAvailable: nfc);

/// Weighs in and taps the bathroom tag, leaving the shower leg live.
MorningSession inBathroom() => fresh()
  ..enterWeight(72, t0)
  ..onTag(SessionTagSlot.bathroom, t0.add(const Duration(seconds: 30)));

void main() {
  group('start', () {
    test('requires every leg when all tags exist', () {
      final s = fresh();
      expect(s.currentLeg, SessionLeg.bathroomIn);
      expect(s.passedAt, isEmpty);
      expect(s.bathroomTagRequired, isTrue);
      expect(s.date, '2026-09-17');
    });

    test('skips legs whose tag is unregistered', () {
      final s = fresh(
        tags: const SessionTagSettings(tagIds: <String>['bath', '', 'desk']),
      );
      expect(s.passedHow[SessionLeg.dressed], LegPass.skipped);
      expect(s.passedHow.containsKey(SessionLeg.atDesk), isFalse);
    });

    test('without NFC it is a weigh-in and nothing else', () {
      final s = fresh(nfc: false);
      expect(s.bathroomTagRequired, isFalse);
      expect(s.currentLeg, SessionLeg.bathroomIn);
      s.enterWeight(70, t0);
      expect(s.outcome, SessionOutcome.completed);
      expect(s.weightKg, 70);
    });
  });

  group('weigh-in', () {
    test('stays pending until the bathroom tag confirms it', () {
      final s = fresh();
      expect(s.enterWeight(72, t0), contains('tap the bathroom tag'));
      expect(s.weightKg, isNull);
      expect(s.pendingWeightKg, 72);
      s.onTag(SessionTagSlot.bathroom, t0.add(const Duration(minutes: 1)));
      expect(s.weightKg, 72);
      expect(s.pendingWeightKg, isNull);
      expect(s.currentLeg, SessionLeg.showerDone);
    });

    test('a tag without a weight does nothing', () {
      final s = fresh();
      expect(s.onTag(SessionTagSlot.bathroom, t0), contains('Weigh in first'));
      expect(s.currentLeg, SessionLeg.bathroomIn);
    });

    test('a late tag discards the weight', () {
      final s = fresh()..enterWeight(72, t0);
      final late = t0.add(const Duration(minutes: 2, seconds: 1));
      expect(s.onTag(SessionTagSlot.bathroom, late), contains('expired'));
      expect(s.pendingWeightKg, isNull);
      expect(s.currentLeg, SessionLeg.bathroomIn);
    });

    test('the tick expires a pending weight too', () {
      final s = fresh()..enterWeight(72, t0);
      final tick = s.tick(t0.add(const Duration(minutes: 3)));
      expect(tick.changed, isTrue);
      expect(tick.note, contains('expired'));
      expect(s.pendingWeightKg, isNull);
    });

    test('is refused once the leg has passed', () {
      final s = inBathroom();
      expect(s.enterWeight(80, t0), 'Already weighed in');
      expect(s.weightKg, 72);
    });
  });

  group('legs', () {
    test('the wrong room does not advance', () {
      final s = inBathroom();
      expect(s.onTag(SessionTagSlot.desk, t0), 'Not the bathroom tag');
      expect(s.currentLeg, SessionLeg.showerDone);
    });

    test('the shower tag is refused before eight minutes', () {
      final s = inBathroom();
      final early = s
          .legStart(SessionLeg.showerDone)
          .add(const Duration(minutes: 7));
      expect(s.onTag(SessionTagSlot.bathroom, early), contains('Too early'));
      expect(s.currentLeg, SessionLeg.showerDone);
    });

    test('the full walk completes the session', () {
      final s = inBathroom();
      final shower = s.earliest(SessionLeg.showerDone)!;
      s
        ..onTag(SessionTagSlot.bathroom, shower)
        ..onTag(
          SessionTagSlot.wardrobe,
          shower.add(const Duration(minutes: 3)),
        );
      final done = s.onTag(
        SessionTagSlot.desk,
        shower.add(const Duration(minutes: 5)),
      );
      expect(done, contains('complete'));
      expect(s.outcome, SessionOutcome.completed);
      expect(s.currentLeg, isNull);
      expect(s.onTag(SessionTagSlot.desk, shower), 'Session finished');
    });

    test('deadlines follow the previous leg and the shower has its own', () {
      final s = inBathroom();
      final tap1 = s.passedAt[SessionLeg.bathroomIn]!;
      expect(
        s.deadline(SessionLeg.showerDone),
        tap1.add(const Duration(minutes: 18)),
      );
      expect(
        s.earliest(SessionLeg.showerDone),
        tap1.add(const Duration(minutes: 8)),
      );
      expect(
        s.deadline(SessionLeg.bathroomIn),
        t0.add(const Duration(minutes: 10)),
      );
      expect(s.stillnessSuspended, isTrue);
    });
  });

  group('deadlines and re-rings', () {
    test('nothing rings before the deadline', () {
      final s = fresh();
      final tick = s.tick(t0.add(const Duration(minutes: 9)));
      expect(tick.changed, isFalse);
      expect(tick.ringReason, isNull);
      expect(s.nextDeadline(), t0.add(const Duration(minutes: 10)));
    });

    test('the native alarm gets a grace before Dart rings itself', () {
      final s = fresh();
      final deadline = s.deadline(SessionLeg.bathroomIn);
      expect(
        s.tick(deadline.add(const Duration(seconds: 5))).ringReason,
        isNull,
      );
      expect(
        s.tick(deadline.add(const Duration(seconds: 25))).ringReason,
        'deadline:bathroomIn',
      );
    });

    test('a dismissed re-ring marks the leg and bypasses it later', () {
      final s = fresh();
      final deadline = s.deadline(SessionLeg.bathroomIn);
      s.recordReRing(deadline.add(const Duration(minutes: 3)));
      expect(s.reRings, 1);
      expect(s.reRingReasons, <String>['deadline:bathroomIn']);
      expect(s.deadlineRung, <SessionLeg>{SessionLeg.bathroomIn});
      expect(s.nextDeadline(), isNull);
      expect(s.tick(deadline.add(const Duration(minutes: 4))).changed, isFalse);
      final tick = s.tick(deadline.add(const Duration(minutes: 5)));
      expect(tick.note, contains('Skipped'));
      expect(s.passedHow[SessionLeg.bathroomIn], LegPass.bypassed);
      expect(s.currentLeg, SessionLeg.showerDone);
    });

    test(
      'a stillness ring keeps its reason and does not spend the deadline',
      () {
        final s = fresh()
          ..markReRing('still:bathroomIn', t0)
          ..recordReRing(t0.add(const Duration(minutes: 3)));
        expect(s.reRingReasons, <String>['still:bathroomIn']);
        expect(s.deadlineRung, isEmpty);
        expect(s.nextDeadline(), isNotNull);
      },
    );

    test('stillness is due only when live, allowed and not showering', () {
      final s = fresh();
      expect(s.stillnessRingDue(const Duration(minutes: 4)), isTrue);
      expect(s.stillnessRingDue(const Duration(minutes: 3)), isFalse);
      expect(s.stillnessRingDue(null), isFalse);
      expect(
        inBathroom().stillnessRingDue(const Duration(minutes: 9)),
        isFalse,
      );
      s.reRings = MorningSession.maxReRings;
      expect(s.stillnessRingDue(const Duration(minutes: 9)), isFalse);
    });

    test('a miss with no re-rings left fails the session', () {
      final s = fresh()..reRings = MorningSession.maxReRings;
      expect(s.nextDeadline(), isNull);
      final tick = s.tick(s.deadline(SessionLeg.bathroomIn));
      expect(tick.changed, isTrue);
      expect(s.isActive, isFalse);
      expect(s.tick(t0).changed, isFalse);
    });
  });

  group('json', () {
    test('round-trips every field', () {
      final s = inBathroom()
        ..markReRing('still:showerDone', t0)
        ..recordReRing(t0.add(const Duration(minutes: 5)));
      final back = sessionFromJson(s.toJson())!;
      expect(back.toJson(), s.toJson());
      expect(back.currentLeg, SessionLeg.showerDone);
      expect(back.weightKg, 72);
      expect(back.passedHow[SessionLeg.bathroomIn], LegPass.tag);
    });

    test('rejects shapes that are not a session', () {
      expect(sessionFromJson(<String, Object?>{'date': 1}), isNull);
      expect(sessionFromJson('x'), isNull);
    });

    test('tolerates missing optionals', () {
      final s = sessionFromJson(<String, Object?>{
        'date': '2026-09-17',
        'started_at': t0.toIso8601String(),
        'passed': <String, Object?>{
          'dressed': <String, Object?>{'at': 'garbage'},
          'atDesk': <String, Object?>{'at': t0.toIso8601String()},
        },
        'deadline_rung': <Object?>['nope', 'atDesk'],
      })!;
      expect(s.updatedAt, t0);
      expect(s.passedAt.keys, <SessionLeg>[SessionLeg.atDesk]);
      expect(s.passedHow[SessionLeg.atDesk], LegPass.tag);
      expect(s.deadlineRung, <SessionLeg>{SessionLeg.atDesk});
      expect(s.outcome, SessionOutcome.active);
    });
  });
}
