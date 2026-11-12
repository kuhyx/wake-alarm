import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/home_history_card.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';
import 'package:wake_alarm_sync/ui/dashed_slot.dart';
import 'package:wake_alarm_sync/ui/spoken_label.dart';

MorningSession _session(
  DateTime at, {
  double? kg,
  int reRings = 0,
  SessionOutcome outcome = SessionOutcome.completed,
}) =>
    SessionRules.start(
        now: at,
        tags: const SessionTagSettings(),
        nfcAvailable: false,
      )
      ..weightKg = kg
      ..reRings = reRings
      ..outcome = outcome;

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('describes a morning in one line', () {
    expect(
      describeMorning(
        _session(DateTime(2026, 9, 17, 8), kg: 72.4, reRings: 1),
        previousWeight: 72.7,
      ),
      '09-17 ✓ 1 re-ring · 72.4 kg (−0.3)',
    );
    expect(
      describeMorning(
        _session(
          DateTime(2026, 9, 16, 8),
          kg: 73,
          outcome: SessionOutcome.failed,
        ),
        previousWeight: 72,
      ),
      '09-16 ✗ 0 re-rings · 73.0 kg (+1.0)',
    );
    expect(
      describeMorning(
        _session(DateTime(2026, 9, 15, 8), kg: 72),
        previousWeight: 72,
      ),
      '09-15 ✓ 0 re-rings · 72.0 kg (±0.0)',
    );
    expect(
      describeMorning(
        _session(DateTime(2026, 9, 14, 8), outcome: SessionOutcome.active),
      ),
      '09-14 … 0 re-rings',
    );
    expect(
      describeMorning(_session(DateTime(2026, 9, 13, 8), kg: 72)..energy = 4),
      '09-13 ✓ 0 re-rings · 72.0 kg · energy 4/5',
    );
  });

  testWidgets('is absent until a morning has finished', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: HomeHistoryCard()));
    await tester.pump();
    expect(find.byType(Row), findsNothing);
    expect(find.byType(DashedSlot), findsNothing);
  });

  testWidgets('shows an empty slot when no morning has finished', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(home: HomeHistoryCard(emptyText: 'None yet.')),
    );
    expect(find.byType(DashedSlot), findsNothing);
    await tester.pump();
    expect(find.byType(DashedSlot), findsOneWidget);
    expect(
      tester.widget<SpokenLabel>(find.byType(SpokenLabel).first).semanticLabel,
      'None yet.',
    );
  });

  testWidgets('lists the last seven with weight deltas', (tester) async {
    final store = SessionStore();
    for (var day = 1; day <= 9; day++) {
      await store.archive(_session(DateTime(2026, 9, day, 8), kg: 70.0 + day));
    }
    // As the home tile shows it: a scrolling bottom sheet.
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: SingleChildScrollView(child: HomeHistoryCard())),
      ),
    );
    await tester.pump();
    final rows = tester
        .widgetList<SpokenLabel>(find.byType(SpokenLabel))
        .map((w) => w.semanticLabel)
        .toList();
    expect(rows, hasLength(kHistoryShown));
    expect(rows.first, '09-09 ✓ 0 re-rings · 79.0 kg (+1.0)');
    expect(find.text('79.0'), findsOneWidget);
    expect(find.text(' (+1.0)'), findsWidgets);
    expect(find.text('09-03'), findsOneWidget);
    expect(find.text('09-02'), findsNothing);
  });
}
