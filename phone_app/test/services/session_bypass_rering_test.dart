import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

final DateTime t0 = DateTime(2026, 9, 17, 8, 5);

MorningSession fresh() => SessionRules.start(
  now: t0,
  tags: const SessionTagSettings(tagIds: <String>['bath', 'ward', 'desk']),
  nfcAvailable: true,
);

void main() {
  test('a bypass re-ring is named for its cause and counted once', () {
    final s = fresh()
      ..markReRing('deadline:bathroomIn', t0)
      ..adoptBypassReRing('fsi_revoked')
      ..recordReRing(t0.add(const Duration(minutes: 3)));
    expect(s.reRings, 1);
    expect(s.reRingReasons, <String>['bypass:fsi_revoked']);
  });

  test('no bypass stamped keeps the deadline reason', () {
    final s = fresh()
      ..markReRing('deadline:bathroomIn', t0)
      ..adoptBypassReRing(null)
      ..recordReRing(t0.add(const Duration(minutes: 3)));
    expect(s.reRingReasons, <String>['deadline:bathroomIn']);
  });
}
