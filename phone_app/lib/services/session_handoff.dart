import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

/// What the ring screen does once the dismiss sequence is satisfied.
///
/// The ring no longer ends the morning. The first dismiss of the day starts
/// the session; the dismiss of a re-ring resumes it, one re-ring richer.
/// Either way the ring screen hands over to the session screen instead of
/// closing the activity — the activity is what keeps NFC and the screen on.
class SessionHandoff {
  /// Creates a handoff; every dependency is injectable for tests.
  SessionHandoff({
    required this.scheduler,
    SessionStore? store,
    DateTime Function()? now,
  }) : store = store ?? SessionStore(),
       _now = now ?? DateTime.now;

  /// Platform bridge, for the NFC availability check.
  final AlarmScheduler scheduler;

  /// Session persistence.
  final SessionStore store;

  final DateTime Function() _now;

  /// Starts or resumes today's session; false when the ring should just end.
  ///
  /// [away] is the ring's verdict that the phone is not at home: no scale,
  /// no tags, no session. A live session from a *previous* day is archived
  /// as it stands (failed, since it never finished) rather than resumed —
  /// yesterday's clocks would re-ring the moment the screen came up.
  Future<bool> afterDismiss({required bool away}) async {
    // Reaching this call at all means the dismiss gate was satisfied --
    // recorded before anything else so an interrupted await below still
    // leaves the native side knowing the ring was answered.
    await scheduler.markRingDismissed();
    final now = _now();
    final today = SessionRules.dateKey(now);
    final current = await store.loadCurrent();
    if (current != null && current.date == today) {
      if (!current.isActive) return false;
      current.recordReRing(now);
      await store.save(current);
      return true;
    }
    if (current != null) {
      current
        ..outcome = SessionOutcome.failed
        ..updatedAt = now;
      await store.archive(current);
    }
    if (away) return false;
    // One session per day. A ring after today's has finished (a probe, or
    // the alarm moved earlier and rung twice) must not start the morning
    // over -- the weigh-in and the walk have been done.
    final history = await store.history();
    if (history.any((s) => s.date == today)) return false;
    final session = SessionRules.start(
      now: now,
      tags: await SessionTagSettings.load(),
      nfcAvailable: await scheduler.hasNfc(),
    );
    await store.save(session);
    return true;
  }
}
