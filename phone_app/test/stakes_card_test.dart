import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/home_body.dart';
import 'package:wake_alarm_sync/screens/stakes_card.dart';
import 'package:wake_alarm_sync/services/escape_log.dart';
import 'package:wake_alarm_sync/services/stakes.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/dashed_slot.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

import 'fake_enforcement_channel.dart';

/// Every row's spoken sentence: the card paints glyphs, the words are here.
List<String> spoken(WidgetTester tester) => tester
    .widgetList<SpokenLabel>(find.byType(SpokenLabel))
    .map((w) => w.semanticLabel)
    .toList();

/// The escape outcome, now a StatusCue.
String cueWords(WidgetTester tester) =>
    tester.widget<StatusCue>(find.byType(StatusCue)).semanticLabel;

final Finder escapeButton = find.byKey(const Key('stakes-escape'));

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
    final words = spoken(tester);
    expect(words, contains('Today · Thu 1 Oct — stick day'));
    expect(words.where((w) => w.contains('no dismiss by 07:15')), hasLength(1));
    expect(words.where((w) => w.contains('PC rings at 07:02')), hasLength(1));
    expect(words, contains('Apps locked through Fri 2 Oct.'));
    expect(words, contains('Streak: 1 missed stick day in a row'));
    // Painted: the gavel day, the deadline, the lock date and the streak.
    expect(find.byIcon(Icons.gavel_outlined), findsOneWidget);
    expect(find.text('07:15'), findsOneWidget);
    expect(find.text('02.10'), findsWidgets);
    expect(find.text('1'), findsOneWidget);
    expect(escapeButton, findsOneWidget);
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
    final words = spoken(tester);
    expect(words.where((w) => w.contains('Finish the morning by 09:27')), [
      isNotEmpty,
    ]);
    expect(words.where((w) => w.contains('PC rings at 07:59')), hasLength(1));
    expect(find.text('09:27'), findsOneWidget);
    expect(find.text('07:59'), findsOneWidget);
  });

  testWidgets('the escape button is gone after the last day', (tester) async {
    native.state = nativeState(today: '2026-10-16');
    await pumpCard(tester, now: DateTime(2026, 10, 16, 6));
    expect(escapeButton, findsNothing);
  });

  testWidgets('the escape button is disabled while syncing', (tester) async {
    native.state = nativeState();
    await pumpCard(tester, busy: true);
    expect(tester.widget<IconButton>(escapeButton).onPressed, isNull);
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
    await tester.tap(escapeButton);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    FilledButton confirm() =>
        tester.widget<FilledButton>(find.byKey(const Key('escape-confirm')));
    expect(confirm().onPressed, isNull);
    await tester.enterText(find.byType(TextField), 'too short');
    await tester.pump();
    expect(confirm().onPressed, isNull);
    expect(find.text('9/$escapeReasonMinChars'), findsOneWidget);

    const reason = 'The tag on the bathroom wall fell off overnight.';
    await tester.enterText(find.byType(TextField), reason);
    await tester.pump();
    expect(confirm().onPressed, isNotNull);
    await tester.tap(find.byKey(const Key('escape-confirm')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(native.methods, contains('escapeToday'));
    expect((await EscapeLog.load()).single['reason'], reason);
    expect(escaped, 1);
    expect(cueWords(tester), startsWith('Excused'));
    expect(
      tester.widget<StatusCue>(find.byType(StatusCue)).resolvedKind,
      CueKind.ok,
    );
  });

  testWidgets('cancelling the dialog changes nothing', (tester) async {
    native.state = nativeState();
    final escaped = await pumpCard(tester);
    await tester.tap(escapeButton);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.byKey(const Key('escape-cancel')));
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
    await tester.tap(escapeButton);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.enterText(find.byType(TextField), 'y' * escapeReasonMinChars);
    await tester.pump();
    await tester.tap(find.byKey(const Key('escape-confirm')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(cueWords(tester), contains('refused'));
    expect(
      tester.widget<StatusCue>(find.byType(StatusCue)).resolvedKind,
      CueKind.error,
    );
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
    expect(find.byType(DashedSlot), findsNothing);
    await tester.pump();
    expect(find.byType(DashedSlot), findsOneWidget);
    expect(spoken(tester).first, 'No stakes.');
  });
}
