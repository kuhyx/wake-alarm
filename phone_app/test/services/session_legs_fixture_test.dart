import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';

/// The PC reads leg names (the keys of the published `passed` map) and labels
/// (its `next_step`) from the same literal: the Python half asserts it in
/// `wake_alarm/tests/test_session_legs.py`. Neither side's own round-trip can
/// catch a rename on the other.
void main() {
  test('SessionLeg names and labels equal the shared fixture', () {
    final raw = File(
      '../wake_alarm/tests/fixtures/session_legs.json',
    ).readAsStringSync();
    final legs = ((jsonDecode(raw) as Map<String, Object?>)['legs']! as List)
        .cast<Map<String, dynamic>>();
    expect(
      <(String, String)>[for (final l in SessionLeg.values) (l.name, l.label)],
      <(String, String)>[
        for (final l in legs) (l['name'] as String, l['label'] as String),
      ],
    );
  });
}
