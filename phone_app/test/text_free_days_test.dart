import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/screens/free_days_screen.dart';
import 'package:wake_alarm_sync/screens/sick_day_sheet.dart';
import 'package:wake_alarm_sync/screens/sick_days_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_sync.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

import 'text_free_support.dart';

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

  group('settings-type screens — free/sick days', () {
    testWidgets('FreeDaysScreen has no words on screen', (tester) async {
      phoneView(tester);
      const channel = MethodChannel(AlarmScheduler.channelName);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async => null);
      final scheduler = AlarmScheduler(channel: channel);
      final pool = await FreeDayPool.open(
        persistence: _MemPersistence(),
        deviceId: 'phone',
      );
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: FreeDaysScreen(
            openPool: () async => pool,
            syncer: FreeDaySync(
              openClient: () async => null,
              scheduler: scheduler,
            ),
            openSickPool: () => SickDayPool.open(
              persistence: _MemPersistence(),
              deviceId: 'phone',
            ),
            sickSyncer: SickDaySync(
              openClient: () async => null,
              scheduler: scheduler,
            ),
            now: () => _today,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expectNoWords(tester, 'FreeDaysScreen');
    });

    testWidgets('SickDaysScreen has no words on screen', (tester) async {
      phoneView(tester);
      final caches = <List<String>>[];
      const cacheUnreadable = false;
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
      final scheduler = AlarmScheduler(channel: channel);
      final sick = await SickDayPool.open(
        persistence: _MemPersistence(),
        deviceId: 'phone',
      );
      final free = await FreeDayPool.open(
        persistence: _MemPersistence(),
        deviceId: 'phone',
      );
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: SickDaysScreen(
            openPool: () async => sick,
            syncer: SickDaySync(
              openClient: () async => null,
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
      expectNoWords(tester, 'SickDaysScreen');
    });

    testWidgets('SickDaySheet has no words on screen', (tester) async {
      phoneView(tester);
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: Scaffold(
            body: Center(
              child: IconButton(
                key: const Key('open'),
                onPressed: () => showSickDaySheet(
                  tester.element(find.byKey(const Key('open'))),
                  day: DateTime(2026, 11, 20),
                  isSick: false,
                  kept: const <String>{},
                ),
                icon: const Icon(Icons.open_in_new),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.byKey(const Key('open')));
      await tester.pumpAndSettle();
      expectNoWords(tester, 'SickDaySheet');
    });
  });
}
