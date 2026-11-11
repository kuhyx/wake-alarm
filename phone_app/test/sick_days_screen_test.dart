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
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/dashed_slot.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

import 'fake_day_pool_store.dart';

final _today = DateTime(2026, 10, 16);

Finder iconLabelled(String label) =>
    find.byWidgetPredicate((w) => w is Icon && w.semanticLabel == label);

String statusOf(WidgetTester tester) =>
    tester.widget<StatusCue>(find.byType(StatusCue).first).semanticLabel;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late AlarmScheduler scheduler;
  late SickDayPool sick;
  late FreeDayPool free;
  late int syncs;
  late List<List<String>> caches;
  late bool cacheUnreadable;

  setUp(() async {
    caches = [];
    cacheUnreadable = false;
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'setSickDays') {
            caches.add(
              ((call.arguments as Map)['dates'] as List).cast<String>(),
            );
          }
          if (call.method == 'getSickDays' && !cacheUnreadable) {
            return caches.isEmpty ? <String>[] : caches.last;
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
      scheduler: scheduler,
    ),
  );

  Finder cell(DateTime day) =>
      find.byKey(ValueKey<String>('sick-day-${FreeDayPool.toIso(day)}'));

  Future<void> tapDay(WidgetTester tester, DateTime day) async {
    await tester.ensureVisible(cell(day));
    await tester.tap(cell(day));
    await tester.pumpAndSettle();
  }

  /// Taps [day], then [button] in the per-locker sheet it opens.
  Future<void> viaSheet(
    WidgetTester tester,
    DateTime day,
    String buttonKey,
  ) async {
    await tapDay(tester, day);
    await tester.tap(find.byKey(Key(buttonKey)));
    await tester.pumpAndSettle();
  }

  Future<void> open(WidgetTester tester, {Widget? widget}) async {
    phoneSize(tester);
    await tester.pumpWidget(widget ?? app());
    await tester.pumpAndSettle();
  }

  testWidgets('every day starts normal; syncs on open', (tester) async {
    await open(tester);
    expect(find.byType(SickDaysScreen), findsOneWidget);
    expect(find.byIcon(Icons.sick_outlined), findsWidgets);
    expect(find.text('10/2026'), findsOneWidget);
    expect(find.byType(DashedSlot), findsOneWidget);
    expect(syncs, 1);
    expect(caches.last, isEmpty);
  });

  testWidgets('today can be marked sick and cleared again', (tester) async {
    await open(tester);

    await viaSheet(tester, _today, 'sick-mark');
    expect(sick.isSick(_today), isTrue);
    expect(find.text('16.10.2026'), findsOneWidget);
    expect(caches.last, ['2026-10-16'], reason: 'native cache rewritten');
    expect(syncs, 2);

    await viaSheet(tester, _today, 'sick-clear');
    expect(sick.isSick(_today), isFalse);
    expect(caches.last, isEmpty);
    expect(syncs, 3);
  });

  testWidgets('the native cache is read back after a mark', (tester) async {
    await open(tester);
    expect(iconLabelled('Alarm cache: none'), findsOneWidget);
    await viaSheet(tester, DateTime(2026, 10, 18), 'sick-mark');
    await viaSheet(tester, DateTime(2026, 10, 17), 'sick-mark');
    expect(iconLabelled('Alarm cache: 2026-10-17, 2026-10-18'), findsOneWidget);
  });

  testWidgets('an unreadable native cache never reads as none', (tester) async {
    cacheUnreadable = true;
    await open(tester);
    expect(iconLabelled('Alarm cache: unreadable'), findsOneWidget);
  });

  testWidgets('a future day is marked in the sick colour', (tester) async {
    await open(tester);
    await viaSheet(tester, DateTime(2026, 10, 20), 'sick-mark');
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
      statusOf(tester),
      contains('2026-10-20 is a free day — release it in Free days first.'),
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
    expect(statusOf(tester), contains('Free-day pool unavailable'));
  });

  testWidgets('month arrows reach January and the end of next year', (
    tester,
  ) async {
    await open(tester);
    for (var i = 0; i < 9; i++) {
      await tester.tap(find.byIcon(Icons.chevron_left));
      await tester.pumpAndSettle();
    }
    expect(find.text('01/2026'), findsOneWidget);
    for (var i = 0; i < 23; i++) {
      await tester.tap(find.byIcon(Icons.chevron_right));
      await tester.pumpAndSettle();
    }
    expect(find.text('12/2027'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.sync));
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
    expect(statusOf(tester), contains('Error: pool unavailable'));
  });
}
