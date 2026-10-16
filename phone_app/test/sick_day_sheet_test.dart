import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/screens/day_calendar.dart';
import 'package:wake_alarm_sync/screens/sick_days_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';
import 'package:wake_alarm_sync/services/sick_day_keep.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_sync.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

import 'fake_day_pool_store.dart';

/// The per-locker sheet on the sick-day calendar (sickdays 0.2.0 keep).
final _today = DateTime(2026, 10, 16);
final _day = DateTime(2026, 10, 20);
bool _never(DateTime _) => false;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late SickDayPool sick;
  late int syncs;
  late List<List<String>> caches;

  setUp(() async {
    caches = [];
    syncs = 0;
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'setSickDays') {
            caches.add(
              ((call.arguments as Map)['dates'] as List).cast<String>(),
            );
          }
          if (call.method == 'getSickDays') {
            return caches.isEmpty ? <String>[] : caches.last;
          }
          return null;
        });
    sick = await SickDayPool.open(
      persistence: MemPersistence(),
      deviceId: 'phone',
    );
  });

  Future<void> open(WidgetTester tester) async {
    tester.view
      ..physicalSize = const Size(1080, 2400)
      ..devicePixelRatio = 2.625;
    addTearDown(tester.view.reset);
    final scheduler = AlarmScheduler(
      channel: const MethodChannel(AlarmScheduler.channelName),
    );
    final free = await FreeDayPool.open(
      persistence: MemPersistence(),
      deviceId: 'phone',
    );
    await tester.pumpWidget(
      MaterialApp(
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
          openFreePool: () async => free,
          freeSyncer: FreeDaySync(
            openClient: () async => null,
            scheduler: scheduler,
          ),
          now: () => _today,
          scheduler: scheduler,
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Finder cell(DateTime day) =>
      find.byKey(ValueKey<String>('sick-day-${FreeDayPool.toIso(day)}'));
  Finder toggle(String locker) => find.byKey(ValueKey<String>('keep-$locker'));
  bool isOn(WidgetTester tester, String locker) =>
      tester.widget<SwitchListTile>(toggle(locker)).value;

  Future<void> tap(WidgetTester tester, Finder finder) async {
    await tester.ensureVisible(finder);
    await tester.pumpAndSettle();
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  testWidgets('a normal day opens with every locker off', (tester) async {
    await open(tester);
    await tap(tester, cell(_day));

    expect(find.text('Mark sick: Tue 2026-10-20'), findsOneWidget);
    for (final locker in SickLocker.all) {
      expect(isOn(tester, locker), isFalse, reason: locker);
    }
    for (final label in [
      'Workout lock',
      'LeetCode',
      'Book',
      'Diet',
      'Wake alarm',
    ]) {
      expect(find.text(label), findsOneWidget);
    }
    expect(find.text('Clear sick day'), findsNothing);
    expect(sick.isSick(_day), isFalse, reason: 'nothing until confirmed');

    await tap(tester, find.text('Mark sick'));
    expect(sick.isSick(_day), isTrue);
    expect(sick.keptLockers(_day), isEmpty);
    expect(caches.last, ['2026-10-20'], reason: 'the alarm stands down');
    expect(syncs, 2);
  });

  testWidgets('switched-on lockers are kept; a kept alarm still rings', (
    tester,
  ) async {
    await open(tester);
    await tap(tester, cell(_day));
    await tap(tester, toggle(SickLocker.alarm));
    await tap(tester, toggle(SickLocker.leetcode));
    await tap(tester, find.text('Mark sick'));

    expect(sick.keptLockers(_day), {SickLocker.alarm, SickLocker.leetcode});
    expect(caches.last, isEmpty);
    expect(find.text('Alarm cache: none'), findsOneWidget);
    final box = tester.widget<DayCell>(cell(_day));
    expect(box.isMarked, isTrue, reason: 'still a sick day');
    expect(box.badge, isTrue, reason: 'kept lockers are badged');
    expect(find.text('Kept: LeetCode, Wake alarm'), findsOneWidget);
  });

  testWidgets('a sick day without kept lockers has no badge', (tester) async {
    await sick.add(_day, isFree: _never, now: _today);
    await open(tester);
    expect(tester.widget<DayCell>(cell(_day)).badge, isFalse);
  });

  testWidgets('a sick day reopens showing its switches', (tester) async {
    await sick.add(_day, isFree: _never, now: _today, keep: ['diet']);
    await open(tester);
    await tap(tester, cell(_day));

    expect(find.text('Sick day: Tue 2026-10-20'), findsOneWidget);
    expect(isOn(tester, SickLocker.diet), isTrue);
    expect(isOn(tester, SickLocker.alarm), isFalse);
    expect(find.text('Save'), findsOneWidget);
    expect(find.text('Clear sick day'), findsOneWidget);
    expect(find.text('Mark sick'), findsNothing);
  });

  testWidgets('Save edits keep only, never state', (tester) async {
    await sick.add(_day, isFree: _never, now: _today);
    final state = sick.snapshot()['2026-10-20']!.fields['state']!;
    await open(tester);
    await tap(tester, cell(_day));
    await tap(tester, toggle(SickLocker.alarm));
    await tap(tester, find.text('Save'));

    final fields = sick.snapshot()['2026-10-20']!.fields;
    expect(fields['state'], state, reason: 'value and HLC untouched');
    expect(fields['keep']!.$1, ['alarm']);
    expect(fields['keep']!.$2 > state.$2, isTrue);
    expect(caches.last, isEmpty, reason: 'the alarm now rings');
    expect(syncs, 2);
  });

  testWidgets('Save with nothing changed writes nothing', (tester) async {
    await sick.add(_day, isFree: _never, now: _today, keep: ['book']);
    final before = sick.snapshot()['2026-10-20'];
    await open(tester);
    await tap(tester, cell(_day));
    await tap(tester, find.text('Save'));
    expect(sick.snapshot()['2026-10-20'], before);
    expect(syncs, 1);
  });

  testWidgets('Clear sick day returns the day to normal', (tester) async {
    await sick.add(_day, isFree: _never, now: _today, keep: ['alarm']);
    await open(tester);
    await tap(tester, cell(_day));
    await tap(tester, find.text('Clear sick day'));

    expect(sick.isSick(_day), isFalse);
    expect(sick.snapshot()['2026-10-20']!.fields['keep']!.$1, isEmpty);
    expect(find.text('None ahead.'), findsOneWidget);
    expect(syncs, 2);
  });

  testWidgets('dismissing the sheet writes nothing', (tester) async {
    await open(tester);
    await tap(tester, cell(_day));
    await tap(tester, toggle(SickLocker.workout));
    await tester.tapAt(const Offset(200, 40));
    await tester.pumpAndSettle();

    expect(find.text('Mark sick'), findsNothing, reason: 'sheet closed');
    expect(sick.isSick(_day), isFalse);
    expect(syncs, 1);
  });

  testWidgets('a past sick day is read-only: no sheet, no edit', (
    tester,
  ) async {
    final hlc = Hlc.newTick('pc');
    await sick.replaceAll({
      '2026-10-15': Record(
        id: '2026-10-15',
        fields: {
          'state': ('sick', hlc),
          'keep': (<Object?>['alarm'], hlc),
        },
      ),
    });
    await open(tester);
    await tap(tester, cell(DateTime(2026, 10, 15)));

    expect(find.byType(SwitchListTile), findsNothing);
    expect(sick.keptLockers(DateTime(2026, 10, 15)), {'alarm'});
    final box = tester.widget<DayCell>(cell(DateTime(2026, 10, 15)));
    expect(box.isPast && box.isMarked && box.badge, isTrue);
    expect(syncs, 1);
  });
}
