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
  ..enterCheckIn(72, 3, t0)
  ..onTag(SessionTagSlot.bathroom, t0.add(const Duration(seconds: 30)));

void main() {
  group('catch-up', () {
    test('a later tag catches up a forgotten shower tag', () {
      final s = inBathroom();
      final late = s
          .earliest(SessionLeg.showerDone)!
          .add(const Duration(minutes: 4));
      expect(
        s.onTag(SessionTagSlot.wardrobe, late),
        'Done: ${SessionLeg.dressed.label}',
      );
      expect(s.passedHow[SessionLeg.showerDone], LegPass.caughtUp);
      expect(s.passedHow[SessionLeg.dressed], LegPass.tag);
      expect(s.currentLeg, SessionLeg.atDesk);
      expect(s.nextDeadline(), late.add(MorningSession.legWindow));
      expect(s.reRings, 0);
    });

    test('the desk tag catches up every leg before it', () {
      final s = inBathroom();
      final late = s.earliest(SessionLeg.showerDone)!;
      expect(s.onTag(SessionTagSlot.desk, late), contains('complete'));
      expect(s.passedHow[SessionLeg.showerDone], LegPass.caughtUp);
      expect(s.passedHow[SessionLeg.dressed], LegPass.caughtUp);
      expect(s.outcome, SessionOutcome.completed);
    });

    test('catch-up still waits out the shower floor', () {
      final s = inBathroom();
      final early = s
          .earliest(SessionLeg.showerDone)!
          .subtract(const Duration(seconds: 1));
      expect(s.onTag(SessionTagSlot.wardrobe, early), 'Not the bathroom tag');
      expect(s.currentLeg, SessionLeg.showerDone);
    });

    test('the weigh-in is never caught up', () {
      final s = fresh()..enterCheckIn(72, 3, t0);
      expect(s.onTag(SessionTagSlot.desk, t0), 'Not the bathroom tag');
      expect(s.currentLeg, SessionLeg.bathroomIn);
    });

    test('a caught-up leg survives the store', () {
      final s = inBathroom()
        ..onTag(SessionTagSlot.wardrobe, t0.add(const Duration(minutes: 9)));
      final back = sessionFromJson(s.toJson())!;
      expect(back.passedHow[SessionLeg.showerDone], LegPass.caughtUp);
    });
  });
}
