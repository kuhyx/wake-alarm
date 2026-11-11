import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';

/// Keeps the native side pointed at the live leg.
///
/// One call re-arms the deadline (`armReRing`) and rewrites the native
/// session record behind the launcher redirect and the ongoing notification
/// (`updateSessionNotice`). They are one operation on purpose: a leg whose
/// deadline moved but whose notice did not would show a countdown to an
/// instant nothing rings at, and the reverse would let the notification
/// promise a ring the alarm never arms.
///
/// Called on every change to the session, never per tick -- the countdown
/// is the notification's own.
///
/// A session that is over gets no notice: the finish path clears the record
/// and the notification, and this must not race it back into existence --
/// the tick that noticed the last leg pass ran `_finish` while the tag's
/// own commit was still on its way here (emulator, 2026-09-17), and the
/// stale "Done" record then redirected the next launch into a second
/// session for the day.
Future<void> pointNativeAtLeg(
  AlarmScheduler scheduler,
  MorningSession session,
) async {
  final deadline = session.nextDeadline();
  await scheduler.armReRing(deadline);
  if (!session.isActive) return;
  await scheduler.updateSessionNotice(
    date: session.date,
    label: noticeLabel(session),
    deadline: deadline,
  );
}

/// The notification's one line: glyph + position count, with a running-clock
/// marker when the re-ring was spent.
String noticeLabel(MorningSession session) {
  final leg = session.currentLeg!;
  final glyphs = <SessionLeg, String>{
    SessionLeg.bathroomIn: '🛁',
    SessionLeg.showerDone: '🚿',
    SessionLeg.dressed: '👕',
    SessionLeg.atDesk: '🪑',
  };
  final glyph = glyphs[leg] ?? '•';
  var text = '$glyph ${leg.index + 1}/${SessionLeg.values.length}';
  if (session.deadlineRung.contains(leg)) {
    text += ' ⏳';
  }
  return text;
}
