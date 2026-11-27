import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_arming.dart';
import 'package:wake_alarm_sync/services/alarm_publisher.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';

import '../e2e_support.dart';
import '../fake_day_pool_store.dart';
import '../fake_secure_storage.dart';

/// Persistence whose writes start failing once [failing] is set.
class _FailingWrites extends MemPersistence {
  bool failing = false;

  @override
  Future<void> write(String value) async {
    if (failing) throw const FileSystemException('disk gone');
    await super.write(value);
  }
}

/// Records the platform arms instead of touching the real channel.
class _RecordingScheduler extends AlarmScheduler {
  _RecordingScheduler() : super(channel: const MethodChannel('test/alarm'));

  final List<String> calls = [];

  @override
  Future<bool> canUseFullScreenIntent() async => true;

  @override
  Future<void> schedule(int hour, int minute) async {
    calls.add('schedule $hour:$minute');
  }
}

/// Completes the Clock handoff without launching an intent.
class _RecordingArming extends AlarmArming {
  _RecordingArming(super.scheduler);

  @override
  Future<bool> registerWithClockApp(int hour, int minute) async => true;
}

class _OfflineClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) =>
      throw http.ClientException('offline');
}

Future<AlarmSyncService> _service({LogPersistence? persistence}) =>
    AlarmSyncService.open(
      persistence: persistence ?? MemPersistence(),
      deviceId: 'test-device',
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    installFakeSecureStorage();
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('an unconfigured install is told to connect a backend', () async {
    final scheduler = _RecordingScheduler();
    final service = await _service();
    final message = await AlarmPublisher(
      arming: _RecordingArming(scheduler),
    ).publish(service: service, hour: 8, minute: 0);
    // Offline-first: the time is stored locally and the phone is armed even
    // though nothing can be pushed yet.
    expect(service.currentAlarm, (hour: 8, minute: 0));
    expect(message, contains('Armed for 08:00'));
    expect(message, contains('Connect a sync backend'));
    expect(scheduler.calls, ['schedule 8:0']);
  });

  test('a missing store is not reported as a missing backend', () async {
    // The regression this guards. Both causes used to return the same
    // "connect a backend" line, so a store that failed to open looked like a
    // setup step the user had never done — while Firebase was connected the
    // whole time and the real fault was a null service. The advice pointed at
    // something that was not broken, and nothing published for weeks.
    SharedPreferences.setMockInitialValues(<String, Object>{
      'github_token': 'ghp_configured',
    });
    final scheduler = _RecordingScheduler();
    final message = await AlarmPublisher(
      arming: _RecordingArming(scheduler),
    ).publish(service: null, hour: 8, minute: 0);
    expect(message, contains('Armed for 08:00'));
    expect(message, isNot(contains('Connect a sync backend')));
    expect(message, contains('Sync store unavailable'));
    expect(scheduler.calls, ['schedule 8:0']);
  });

  test('a failed push keeps the phone armed and says it will sync', () async {
    installE2eTestStorage();
    SharedPreferences.setMockInitialValues(<String, Object>{
      'github_token': 'ghp_configured',
    });
    final scheduler = _RecordingScheduler();
    final service = await _service();
    final message = await AlarmPublisher(arming: _RecordingArming(scheduler))
        .publish(
          service: service,
          hour: 7,
          minute: 30,
          httpClient: _OfflineClient(),
        );
    expect(service.currentAlarm, (hour: 7, minute: 30));
    expect(message, contains('Armed for 07:30'));
    expect(message, contains('Saved locally'));
    expect(message, contains('Error'));
    expect(scheduler.calls, ['schedule 7:30']);
  });

  test('a failed local save is reported, never "synced"', () async {
    installE2eTestStorage();
    SharedPreferences.setMockInitialValues(<String, Object>{
      'github_token': 'ghp_configured',
    });
    final github = MemGitHub();
    final persistence = _FailingWrites();
    final service = await _service(persistence: persistence);
    persistence.failing = true;
    final message =
        await AlarmPublisher(
          arming: _RecordingArming(_RecordingScheduler()),
        ).publish(
          service: service,
          hour: 6,
          minute: 45,
          httpClient: github.httpClient,
        );
    expect(message, contains('Armed for 06:45'));
    expect(message, contains('Error'));
    expect(message, isNot(contains('Synced')));
    expect(github.putPaths, isEmpty);
  });

  test('a push on a live mirror ends with the synced line', () async {
    installE2eTestStorage();
    SharedPreferences.setMockInitialValues(<String, Object>{
      'github_token': 'ghp_configured',
    });
    final github = MemGitHub();
    final scheduler = _RecordingScheduler();
    final message = await AlarmPublisher(arming: _RecordingArming(scheduler))
        .publish(
          service: await _service(),
          hour: 7,
          minute: 15,
          httpClient: github.httpClient,
        );
    expect(message, 'Armed for 07:15. Synced to PC ✓ Clock app set ✓');
    expect(scheduler.calls, ['schedule 7:15']);
    expect(github.putPaths, isNotEmpty);
  });

  test('the Clock line names the time only when the handoff completed', () {
    expect(
      syncedStatus(6, 5, inClock: true),
      'Armed for 06:05. Synced to PC ✓ Clock app set ✓',
    );
    expect(
      syncedStatus(6, 5, inClock: false),
      'Armed for 06:05. Synced to PC ✓',
    );
  });
}
