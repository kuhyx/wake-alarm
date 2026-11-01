import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/home_body.dart';
import 'package:wake_alarm_sync/screens/stakes_card.dart';
import 'package:wake_alarm_sync/services/escape_log.dart';
import 'package:wake_alarm_sync/services/stakes.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

import 'fake_enforcement_channel.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FakeEnforcementChannel native;
  final thursday = DateTime(2026, 10, 1, 6, 50);

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    native = FakeEnforcementChannel()..install();
  });

  Future<int> pumpCard(
    WidgetTester tester, {
    DateTime? now,
    bool busy = false,
  }) async {
    var escaped = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: Scaffold(
          body: SingleChildScrollView(
            child: StakesCard(
              now: () => now ?? thursday,
              nextAlarm: () async => (hour: 6, minute: 59),
              onEscaped: () => escaped++,
              busy: busy,
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    return escaped;
  }

  testWidgets('states the stick day, what is pending and the streak', (
    tester,
  ) async {
    native.state = nativeState(
      streak: 1,
      lockedThrough: '2026-10-02',
      lastMiss: '2026-09-30',
    );
    await pumpCard(tester);
    expect(find.text('Today · Thu 1 Oct — stick day'), findsOneWidget);
    expect(find.textContaining('no dismiss by 07:15'), findsOneWidget);
    expect(find.textContaining('PC rings at 07:02'), findsOneWidget);
    expect(find.text('Apps locked through Fri 2 Oct.'), findsOneWidget);
    expect(find.text('Streak: 1 missed stick day in a row'), findsOneWidget);
    expect(find.text('That was a bug'), findsOneWidget);
  });

  testWidgets('absent when the native side answers nothing', (tester) async {
    await pumpCard(tester);
    expect(find.byType(Card), findsNothing);
  });

  testWidgets('absent, not broken, with no channel at all', (tester) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(native.channel, null);
    await pumpCard(tester);
    expect(find.byType(Card), findsNothing);
  });

  testWidgets('tomorrow defaults to the alarm policy', (tester) async {
    native.state = nativeState(dismissedToday: true);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: StakesCard(now: () => thursday)),
      ),
    );
    await tester.pump();
    // Friday's ramp with only the seed minutes earned: 07:57.
    expect(find.textContaining('Finish the morning by 09:27'), findsOneWidget);
    expect(find.textContaining('PC rings at 07:59'), findsOneWidget);
  });

  testWidgets('the escape button is gone after the last day', (tester) async {
    native.state = nativeState(today: '2026-10-16');
    await pumpCard(tester, now: DateTime(2026, 10, 16, 6));
    expect(find.text('That was a bug'), findsNothing);
  });

  testWidgets('the escape button is disabled while syncing', (tester) async {
    native.state = nativeState();
    await pumpCard(tester, busy: true);
    final button = tester.widget<TextButton>(
      find.ancestor(
        of: find.text('That was a bug'),
        matching: find.byWidgetPredicate((w) => w is TextButton),
      ),
    );
    expect(button.onPressed, isNull);
  });

  testWidgets('escaping needs a long reason, then lifts and publishes', (
    tester,
  ) async {
    native.state = nativeState();
    var escaped = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: Scaffold(
          body: StakesCard(
            now: () => thursday,
            nextAlarm: () async => null,
            onEscaped: () => escaped++,
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.tap(find.text('That was a bug'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    FilledButton confirm() =>
        tester.widget<FilledButton>(find.byType(FilledButton));
    expect(confirm().onPressed, isNull);
    await tester.enterText(find.byType(TextField), 'too short');
    await tester.pump();
    expect(confirm().onPressed, isNull);
    expect(find.text('9 / $escapeReasonMinChars characters'), findsOneWidget);

    const reason = 'The tag on the bathroom wall fell off overnight.';
    await tester.enterText(find.byType(TextField), reason);
    await tester.pump();
    expect(confirm().onPressed, isNotNull);
    await tester.tap(find.text('Excuse this morning'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(native.methods, contains('escapeToday'));
    expect((await EscapeLog.load()).single['reason'], reason);
    expect(escaped, 1);
    expect(find.textContaining('Excused'), findsOneWidget);
  });

  testWidgets('cancelling the dialog changes nothing', (tester) async {
    native.state = nativeState();
    final escaped = await pumpCard(tester);
    await tester.tap(find.text('That was a bug'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text('Cancel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(native.methods, isNot(contains('escapeToday')));
    expect(escaped, 0);
  });

  testWidgets('a refused escape says so and does not publish', (tester) async {
    native
      ..state = nativeState()
      ..escapeResult = false;
    await pumpCard(tester);
    await tester.tap(find.text('That was a bug'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.enterText(find.byType(TextField), 'y' * escapeReasonMinChars);
    await tester.pump();
    await tester.tap(find.text('Excuse this morning'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining('refused'), findsOneWidget);
    expect(await EscapeLog.load(), isEmpty);
  });

  testWidgets('the home body opens the card from its tile', (tester) async {
    native.state = nativeState();
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: Scaffold(
          body: HomeBody(
            time: '07:00',
            baseline: '07:00',
            isOverridden: false,
            busy: false,
            status: '',
            configured: true,
            onPickEarlier: () {},
          ),
        ),
      ),
    );
    await tester.pump();
    expect(find.byType(StakesCard), findsNothing);
    await tester.tap(find.byKey(const Key('home-tile-stakes')));
    await tester.pumpAndSettle();
    expect(find.byType(StakesCard), findsOneWidget);
  });

  testWidgets('says so when the native side answers nothing', (tester) async {
    native.state = null;
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: StakesCard(emptyText: 'No stakes.')),
      ),
    );
    expect(find.text('No stakes.'), findsNothing);
    await tester.pump();
    expect(find.text('No stakes.'), findsOneWidget);
  });
}
