import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/screens/free_days_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_sync.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

import 'fake_day_pool_store.dart';

final _today = DateTime(2026, 10, 16);

String statusOf(WidgetTester tester) =>
    tester.widget<StatusCue>(find.byType(StatusCue).first).semanticLabel;

/// The free-day picker's half of "a date is never in both pools".
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late AlarmScheduler scheduler;
  late FreeDayPool free;

  setUp(() async {
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async => null);
    scheduler = AlarmScheduler(channel: channel);
    free = await FreeDayPool.open(
      persistence: MemPersistence(),
      deviceId: 'phone',
    );
  });

  Future<void> pumpScreen(
    WidgetTester tester,
    Future<SickDayPool> Function() openSick,
  ) async {
    tester.view
      ..physicalSize = const Size(1080, 2400)
      ..devicePixelRatio = 2.625;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: FreeDaysScreen(
          openPool: () async => free,
          syncer: FreeDaySync(
            openClient: () async => null,
            scheduler: scheduler,
          ),
          openSickPool: openSick,
          sickSyncer: SickDaySync(
            openClient: () async => null,
            scheduler: scheduler,
          ),
          now: () => _today,
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> tapDay(WidgetTester tester, DateTime day) async {
    final cell = find.byKey(
      ValueKey<String>('free-day-${FreeDayPool.toIso(day)}'),
    );
    await tester.ensureVisible(cell);
    await tester.tap(cell);
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView), const Offset(0, 3000));
    await tester.pumpAndSettle();
  }

  testWidgets('a sick day is refused, naming the sick-day pool', (
    tester,
  ) async {
    final sick = await SickDayPool.open(
      persistence: MemPersistence(),
      deviceId: 'phone',
    );
    await sick.add(DateTime(2026, 10, 20), isFree: (_) => false, now: _today);
    await pumpScreen(tester, () async => sick);

    await tapDay(tester, DateTime(2026, 10, 20));

    expect(free.isFree(DateTime(2026, 10, 20)), isFalse);
    expect(
      statusOf(tester),
      contains('2026-10-20 is a sick day — clear it in Sick days first.'),
    );
    // A normal day still books.
    await tapDay(tester, DateTime(2026, 10, 21));
    expect(free.isFree(DateTime(2026, 10, 21)), isTrue);
  });

  testWidgets('an unreadable sick-day pool refuses every booking', (
    tester,
  ) async {
    await pumpScreen(
      tester,
      () async => throw const FileSystemException('corrupt'),
    );
    await tapDay(tester, DateTime(2026, 10, 21));
    expect(free.isFree(DateTime(2026, 10, 21)), isFalse);
    expect(statusOf(tester), contains('Sick-day pool unavailable'));
  });
}
