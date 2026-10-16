import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/screens/day_calendar.dart';
import 'package:wake_alarm_sync/screens/sick_days_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_sync.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

import 'fake_day_pool_store.dart';

final _today = DateTime(2026, 10, 16);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late AlarmScheduler scheduler;
  late SickDayPool sick;
  late FreeDayPool free;
  late int syncs;
  late List<List<String>> caches;

  setUp(() async {
    caches = [];
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'setSickDays') {
            caches.add(
              ((call.arguments as Map)['dates'] as List).cast<String>(),
            );
          }
          return null;
        });
    scheduler = AlarmScheduler(channel: channel);
    sick = await SickDayPool.open(
      persistence: MemPersistence(),
      deviceId: 'phone',
    );
    free = await FreeDayPool.open(
      persistence: MemPersistence(),
      deviceId: 'phone',
    );
    syncs = 0;
  });

  void phoneSize(WidgetTester tester) {
    tester.view
      ..physicalSize = const Size(1080, 2400)
      ..devicePixelRatio = 2.625;
    addTearDown(tester.view.reset);
  }

  Widget app({Future<FreeDayPool> Function()? openFree}) => MaterialApp(
    theme: buildAppTheme(),
    home: SickDaysScreen(
      openPool: () async => sick,
      syncer: SickDaySync(
        openClient: () async {
          syncs++;
          return null;
        },
        scheduler: scheduler,
      ),
      openFreePool: openFree ?? () async => free,
      freeSyncer: FreeDaySync(
        openClient: () async => null,
        scheduler: scheduler,
      ),
      now: () => _today,
    ),
  );

  Finder cell(DateTime day) =>
      find.byKey(ValueKey<String>('sick-day-${FreeDayPool.toIso(day)}'));

  Future<void> tapDay(WidgetTester tester, DateTime day) async {
    await tester.ensureVisible(cell(day));
    await tester.tap(cell(day));
    await tester.pumpAndSettle();
  }

  Future<void> open(WidgetTester tester, {Widget? widget}) async {
    phoneSize(tester);
    await tester.pumpWidget(widget ?? app());
    await tester.pumpAndSettle();
  }

  testWidgets('every day starts normal; syncs on open', (tester) async {
    await open(tester);
    expect(find.text('Sick days'), findsOneWidget);
    expect(find.byIcon(Icons.sick_outlined), findsOneWidget);
    expect(find.text('October 2026'), findsOneWidget);
    expect(find.text('None ahead.'), findsOneWidget);
    expect(syncs, 1);
    expect(caches.last, isEmpty);
  });

  testWidgets('today can be marked sick and cleared again', (tester) async {
    await open(tester);

    await tapDay(tester, _today);
    expect(sick.isSick(_today), isTrue);
    expect(find.text('Fri 2026-10-16'), findsOneWidget);
    expect(caches.last, ['2026-10-16'], reason: 'native cache rewritten');
    expect(syncs, 2);

    await tapDay(tester, _today);
    expect(sick.isSick(_today), isFalse);
    expect(caches.last, isEmpty);
    expect(syncs, 3);
  });

  testWidgets('a future day is marked in the sick colour', (tester) async {
    await open(tester);
    await tapDay(tester, DateTime(2026, 10, 20));
    expect(sick.isSick(DateTime(2026, 10, 20)), isTrue);
    final box = tester.widget<DayCell>(cell(DateTime(2026, 10, 20)));
    expect(box.markColor, DayMarkColors.dark.sick);
    expect(box.markColor, isNot(buildAppTheme().colorScheme.primary));
  });

  testWidgets('past days are inert', (tester) async {
    await open(tester);
    await tapDay(tester, DateTime(2026, 10, 15));
    expect(sick.isSick(DateTime(2026, 10, 15)), isFalse);
    expect(syncs, 1);
  });

  testWidgets('a free day is refused, naming the free-day pool', (
    tester,
  ) async {
    await free.mark(DateTime(2026, 10, 20), now: _today);
    await open(tester);

    await tapDay(tester, DateTime(2026, 10, 20));

    expect(sick.isSick(DateTime(2026, 10, 20)), isFalse);
    await tester.drag(find.byType(ListView), const Offset(0, 3000));
    await tester.pumpAndSettle();
    expect(
      find.text('2026-10-20 is a free day — release it in Free days first.'),
      findsOneWidget,
    );
    expect(syncs, 1);
  });

  testWidgets('an unreadable free-day pool refuses every mark', (tester) async {
    await open(
      tester,
      widget: app(openFree: () async => throw const FileSystemException('x')),
    );
    await tapDay(tester, DateTime(2026, 10, 20));
    expect(sick.isSick(DateTime(2026, 10, 20)), isFalse);
    await tester.drag(find.byType(ListView), const Offset(0, 3000));
    await tester.pumpAndSettle();
    expect(find.textContaining('Free-day pool unavailable'), findsOneWidget);
  });

  testWidgets('month arrows reach January and the end of next year', (
    tester,
  ) async {
    await open(tester);
    for (var i = 0; i < 9; i++) {
      await tester.tap(find.byTooltip('Previous month'));
      await tester.pumpAndSettle();
    }
    expect(find.text('January 2026'), findsOneWidget);
    for (var i = 0; i < 23; i++) {
      await tester.tap(find.byTooltip('Next month'));
      await tester.pumpAndSettle();
    }
    expect(find.text('December 2027'), findsOneWidget);
    await tester.tap(find.byTooltip('Sync now'));
    await tester.pumpAndSettle();
    expect(syncs, 2);
  });

  testWidgets('a pool that cannot open reports it', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: SickDaysScreen(
          openPool: () async => throw const FileSystemException('ro'),
          now: () => _today,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('Error: pool unavailable'), findsOneWidget);
  });
}
