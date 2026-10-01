import 'package:wake_alarm_sync/services/enforcement_bridge.dart';
import 'package:wake_alarm_sync/services/escape_log.dart';
import 'package:wake_alarm_sync/services/stakes.dart';

/// "That was a bug": excuses this morning, on both halves.
///
/// Native first (`EscapeHatch.kt`): today marked escaped, streak cleared,
/// focus-owner told to lift, `escape_used` + `lift_sent` logged. Then the
/// entry goes into [EscapeLog], which the next sync publishes as `escapes`
/// -- that is what stops a ringing PC and cancels today's PC penalty. The
/// caller triggers that sync.
class EscapeHatch {
  /// Creates the hatch; [bridge] and [now] are injectable for tests.
  EscapeHatch({EnforcementBridge? bridge, DateTime Function()? now})
    : _bridge = bridge ?? EnforcementBridge(),
      _now = now ?? DateTime.now;

  final EnforcementBridge _bridge;
  final DateTime Function() _now;

  /// Whether the hatch is open today.
  bool get isOpen => escapeHatchOpen(_now());

  /// Uses the hatch with [reason]; false when it is closed, the reason is
  /// too short, or the native side refused. Nothing is recorded then.
  Future<bool> use(String reason) async {
    final trimmed = reason.trim();
    if (!isOpen || trimmed.length < escapeReasonMinChars) return false;
    if (!await _bridge.escapeToday()) return false;
    await EscapeLog.add(trimmed, now: _now());
    return true;
  }
}
