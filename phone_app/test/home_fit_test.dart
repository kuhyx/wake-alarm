import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/home_body.dart';
import 'package:wake_alarm_sync/screens/home_history_card.dart';
import 'package:wake_alarm_sync/screens/stakes_card.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

import 'fake_enforcement_channel.dart';

/// The home screen on one phone screen, at Pixel 6a geometry: 1080x2400 px at
/// 2.625, status bar 132 px, nav bar 63 px (from `dumpsys window`).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FakeEnforcementChannel native;
  var picked = 0;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    native = FakeEnforcementChannel()..install();
    picked = 0;
  });

  Future<void> pumpHome(WidgetTester tester, {required String status}) async {
    tester.view
      ..physicalSize = const Size(1080, 2400)
      ..devicePixelRatio = 2.625
      ..padding = const FakeViewPadding(top: 132, bottom: 63);
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: Scaffold(
          appBar: AppBar(
            actions: const [
              Icon(Icons.event_available, semanticLabel: 'Free days'),
              Icon(Icons.sick_outlined, semanticLabel: 'Sick days'),
              Icon(Icons.settings, semanticLabel: 'Settings'),
            ],
          ),
          body: HomeBody(
            time: '07:00',
            baseline: '07:30',
            isOverridden: true,
            busy: false,
            status: status,
            configured: false,
            onPickEarlier: () => picked++,
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  Future<void> seedHistory() async {
    final store = SessionStore();
    for (var day = 1; day <= 9; day++) {
      await store.archive(
        SessionRules.start(
          now: DateTime(2026, 9, day, 8),
          tags: const SessionTagSettings(),
          nfcAvailable: false,
        )..weightKg = 70.0 + day,
      );
    }
  }

  void expectNoVerticalScroll(WidgetTester tester) {
    for (final element in find.byType(Scrollable).evaluate()) {
      final state = (element as StatefulElement).state as ScrollableState;
      if (state.axisDirection == AxisDirection.down ||
          state.axisDirection == AxisDirection.up) {
        expect(state.position.maxScrollExtent, 0, reason: 'vertical scroll');
      }
    }
  }

  testWidgets('worst case fits one screen with the control reachable', (
    tester,
  ) async {
    native.state = nativeState(streak: 1, lockedThrough: '2026-10-02');
    await seedHistory();
    await pumpHome(tester, status: 'Error: ${'x' * 400}');
    expect(tester.takeException(), isNull);
    expectNoVerticalScroll(tester);
    const bottomChrome = 2400 / 2.625 - 63 / 2.625;
    final button = find.byIcon(Icons.arrow_upward);
    expect(tester.getRect(button).bottom, lessThan(bottomChrome));
    await tester.tap(button);
    expect(picked, 1);
  });

  testWidgets('stakes and history sit behind tiles, not on the page', (
    tester,
  ) async {
    native.state = nativeState(streak: 1, lockedThrough: '2026-10-02');
    await seedHistory();
    await pumpHome(tester, status: '');
    expect(find.byType(StakesCard), findsNothing);
    expect(find.byType(HomeHistoryCard), findsNothing);

    await tester.tap(find.byKey(const Key('home-tile-stakes')));
    await tester.pumpAndSettle();
    expect(find.byType(StakesCard), findsOneWidget);
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('home-tile-history')));
    await tester.pumpAndSettle();
    expect(find.byType(HomeHistoryCard), findsOneWidget);
    expect(find.textContaining('09-09'), findsOneWidget);
  });
}
