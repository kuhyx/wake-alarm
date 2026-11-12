import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/screens/free_days_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_sync.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/dashed_slot.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

import 'fake_day_pool_store.dart';

final _today = DateTime(2026, 9, 11);

String statusOf(WidgetTester tester) =>
    tester.widget<StatusCue>(find.byType(StatusCue).first).semanticLabel;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late AlarmScheduler scheduler;
  late FreeDayPool pool;
  late int syncs;

  setUp(() async {
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async => null);
    scheduler = AlarmScheduler(channel: channel);
    pool = await FreeDayPool.open(
      persistence: MemPersistence(),
      deviceId: 'phone',
    );
    syncs = 0;
  });

  /// A Pixel 6a-sized surface, so the header, grid and list all fit.
  void phoneSize(WidgetTester tester) {
    tester.view
      ..physicalSize = const Size(1080, 2400)
      ..devicePixelRatio = 2.625;
    addTearDown(tester.view.reset);
  }

  Widget app() => MaterialApp(
    theme: buildAppTheme(),
    home: FreeDaysScreen(
      openPool: () async => pool,
      syncer: FreeDaySync(
        openClient: () async {
          syncs++;
          return null;
        },
        scheduler: scheduler,
      ),
      openSickPool: () =>
          SickDayPool.open(persistence: MemPersistence(), deviceId: 'phone'),
      sickSyncer: SickDaySync(
        openClient: () async => null,
        scheduler: scheduler,
      ),
      now: () => _today,
    ),
  );

  testWidgets('shows the budget, syncs on open, and lists booked days', (
    tester,
  ) async {
    await pool.mark(DateTime(2026, 9, 20), reason: 'travelling', now: _today);
    // A past free day is not "booked ahead".
    await pool.mark(DateTime(2026, 9, 10), now: DateTime(2026, 9, 10));
    phoneSize(tester);
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    expect(syncs, 1);
    expect(find.text('33/35'), findsOneWidget);
    expect(find.text('20.09.2026'), findsOneWidget);
    expect(find.text('travelling'), findsOneWidget);
    expect(find.textContaining('2026-09-10'), findsNothing);
    expect(
      statusOf(tester),
      contains('Not synced — connect Firebase in Settings.'),
    );
  });

  Finder cell(DateTime day) =>
      find.byKey(ValueKey<String>('free-day-${FreeDayPool.toIso(day)}'));

  /// Scrolls the day into view, then taps it.
  Future<void> tapDay(WidgetTester tester, DateTime day) async {
    await tester.ensureVisible(cell(day));
    await tester.tap(cell(day));
    await tester.pumpAndSettle();
  }

  testWidgets('the list Release gives a future day back and re-syncs', (
    tester,
  ) async {
    await pool.mark(DateTime(2026, 9, 20), now: _today);
    phoneSize(tester);
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey<String>('release-2026-09-20')));
    await tester.pumpAndSettle();

    expect(pool.isFree(DateTime(2026, 9, 20)), isFalse);
    expect(find.text('35/35'), findsOneWidget);
    expect(find.byType(DashedSlot), findsOneWidget);
    expect(syncs, 2);
  });

  testWidgets('the calendar opens on the current month', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    expect(find.text('09/2026'), findsOneWidget);
    expect(find.text('Take a day'), findsNothing);
  });

  testWidgets('tapping a future day books it, no reason asked', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tapDay(tester, DateTime(2026, 9, 12));

    expect(pool.isFree(DateTime(2026, 9, 12)), isTrue);
    expect(pool.reasonFor(DateTime(2026, 9, 12)), '');
    expect(find.text('34/35'), findsOneWidget);
    expect(find.text('12.09.2026'), findsOneWidget);
    expect(syncs, 2);
  });

  testWidgets('tapping a booked future day releases it and refunds', (
    tester,
  ) async {
    await pool.mark(DateTime(2026, 9, 20), now: _today);
    phoneSize(tester);
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();
    expect(find.text('34/35'), findsOneWidget);

    await tapDay(tester, DateTime(2026, 9, 20));

    expect(pool.isFree(DateTime(2026, 9, 20)), isFalse);
    expect(find.text('35/35'), findsOneWidget);
    expect(syncs, 2);
  });

  testWidgets('today and past days are read-only', (tester) async {
    await pool.mark(DateTime(2026, 9, 10), now: DateTime(2026, 9, 10));
    phoneSize(tester);
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tapDay(tester, _today);
    await tapDay(tester, DateTime(2026, 9, 10));
    await tapDay(tester, DateTime(2026, 9, 2));

    expect(pool.isFree(_today), isFalse);
    expect(pool.isFree(DateTime(2026, 9, 10)), isTrue);
    expect(pool.isFree(DateTime(2026, 9, 2)), isFalse);
    expect(syncs, 1);
  });

  testWidgets('month arrows move and stop at the horizon', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    Future<void> press(IconData icon, int times) async {
      for (var i = 0; i < times; i++) {
        await tester.tap(find.byIcon(icon));
        await tester.pumpAndSettle();
      }
    }

    await press(Icons.chevron_right, 1);
    expect(find.text('10/2026'), findsOneWidget);
    await tapDay(tester, DateTime(2026, 10, 2));
    expect(pool.isFree(DateTime(2026, 10, 2)), isTrue);

    // Back to January of this year, and no further.
    await press(Icons.chevron_left, 9);
    expect(find.text('01/2026'), findsOneWidget);
    await press(Icons.chevron_left, 1);
    expect(find.text('01/2026'), findsOneWidget);

    // Forward to December of next year, and no further.
    await press(Icons.chevron_right, 23);
    expect(find.text('12/2027'), findsOneWidget);
    await press(Icons.chevron_right, 1);
    expect(find.text('12/2027'), findsOneWidget);
  });

  testWidgets('a refused booking shows the reason and does not sync', (
    tester,
  ) async {
    // Exhaust the year first.
    for (var i = 0; i < FreeDayPool.annualBudget; i++) {
      await pool.mark(DateTime(2026, 10, 1 + i), now: _today);
    }
    phoneSize(tester);
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();
    expect(find.text('0/35'), findsOneWidget);

    await tapDay(tester, DateTime(2026, 9, 12));

    expect(pool.isFree(DateTime(2026, 9, 12)), isFalse);
    // The 35 booked days make the page long; back to the status line.
    await tester.drag(find.byType(ListView), const Offset(0, 3000));
    await tester.pumpAndSettle();
    expect(statusOf(tester), contains('No free days left in 2026'));
    expect(syncs, 1);
  });

  testWidgets('a pool that cannot open reports it', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: FreeDaysScreen(
          openPool: () async => throw const FileSystemException('ro'),
          syncer: FreeDaySync(
            openClient: () async => null,
            scheduler: scheduler,
          ),
          now: () => _today,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(statusOf(tester), contains('Error: pool unavailable'));
    expect(find.text('Take a day'), findsNothing);
  });
}
