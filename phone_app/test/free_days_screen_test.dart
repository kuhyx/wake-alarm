import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/screens/free_days_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

class _MemPersistence implements LogPersistence {
  String? text;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String value) async => text = value;
}

final _today = DateTime(2026, 9, 11);

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
      persistence: _MemPersistence(),
      deviceId: 'phone',
    );
    syncs = 0;
  });

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
      now: () => _today,
    ),
  );

  testWidgets('shows the budget, syncs on open, and lists booked days', (
    tester,
  ) async {
    await pool.mark(DateTime(2026, 9, 20), reason: 'travelling', now: _today);
    // A past free day is not "booked ahead".
    await pool.mark(DateTime(2026, 9, 10), now: DateTime(2026, 9, 10));
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    expect(syncs, 1);
    expect(find.text('33 of 35'), findsOneWidget);
    expect(find.text('free days left in 2026'), findsOneWidget);
    expect(find.text('Sun 2026-09-20'), findsOneWidget);
    expect(find.text('travelling'), findsOneWidget);
    expect(find.textContaining('2026-09-10'), findsNothing);
    expect(
      find.text('Not synced — connect Firebase in Settings.'),
      findsOneWidget,
    );
  });

  testWidgets('release gives a future day back and re-syncs', (tester) async {
    await pool.mark(DateTime(2026, 9, 20), now: _today);
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Release'));
    await tester.pumpAndSettle();

    expect(pool.isFree(DateTime(2026, 9, 20)), isFalse);
    expect(find.text('35 of 35'), findsOneWidget);
    expect(find.textContaining('Tap "Take a day"'), findsOneWidget);
    expect(syncs, 2);
  });

  testWidgets('take a day walks the date picker and the reason dialog', (
    tester,
  ) async {
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Take a day'));
    await tester.pumpAndSettle();
    expect(find.text('Take a free day'), findsOneWidget);
    // Tomorrow, in the calendar grid of the current month.
    await tester.tap(find.text('12'));
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();

    expect(find.text('Reason (optional)'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'dentist');
    await tester.tap(find.text('Mark free'));
    await tester.pumpAndSettle();

    expect(pool.isFree(DateTime(2026, 9, 12)), isTrue);
    expect(pool.reasonFor(DateTime(2026, 9, 12)), 'dentist');
    expect(find.text('34 of 35'), findsOneWidget);
    expect(find.text('Sat 2026-09-12'), findsOneWidget);
    expect(syncs, 2);
  });

  testWidgets('a refused edit shows the reason and does not sync', (
    tester,
  ) async {
    // Exhaust the year first.
    for (var i = 0; i < FreeDayPool.annualBudget; i++) {
      await pool.mark(DateTime(2026, 10, 1 + i), now: _today);
    }
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();
    expect(find.text('0 of 35'), findsOneWidget);

    await tester.tap(find.text('Take a day'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('12'));
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Mark free'));
    await tester.pumpAndSettle();

    expect(find.textContaining('No free days left in 2026'), findsOneWidget);
    expect(syncs, 1);
  });

  testWidgets('the picker opens even when today is already free', (
    tester,
  ) async {
    await pool.mark(_today, now: _today);
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Take a day'));
    await tester.pumpAndSettle();
    // The cursor moved to the 12th; today is disabled, not asserted on.
    expect(find.text('Take a free day'), findsOneWidget);
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Mark free'));
    await tester.pumpAndSettle();

    expect(pool.isFree(DateTime(2026, 9, 12)), isTrue);
    expect(find.text('33 of 35'), findsOneWidget);
  });

  testWidgets('cancelling the reason dialog marks nothing', (tester) async {
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Take a day'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('12'));
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(pool.freeDays(), isEmpty);
    expect(find.text('35 of 35'), findsOneWidget);
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
    expect(find.textContaining('Error: pool unavailable'), findsOneWidget);
    expect(find.text('Take a day'), findsNothing);
  });
}
