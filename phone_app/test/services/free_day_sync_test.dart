import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';

class _MemPersistence implements LogPersistence {
  String? text;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String value) async => text = value;
}

/// An in-memory `RemoteStore`: a flat path -> text map.
class _MemRemote implements RemoteStore {
  final Map<String, String> files = {};

  @override
  Future<List<String>> listDirectory(String path) async {
    final prefix = '$path/';
    return files.keys
        .where((k) => k.startsWith(prefix))
        .map((k) => k.substring(prefix.length).split('/').first)
        .toSet()
        .toList();
  }

  @override
  Future<String?> getFileText(String path) async => files[path];

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async => files[path] = text;

  @override
  Future<void> deleteFile(String path, {String? message}) async =>
      files.remove(path);

  @override
  Future<bool> canAccessRemote() async => true;

  @override
  void close() {}
}

class _Broken implements RemoteStore {
  @override
  Future<List<String>> listDirectory(String path) async =>
      throw RemoteSyncError('offline');

  @override
  Future<String?> getFileText(String path) async =>
      throw RemoteSyncError('offline');

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async => throw RemoteSyncError('offline');

  @override
  Future<void> deleteFile(String path, {String? message}) async {}

  @override
  Future<bool> canAccessRemote() async => false;

  @override
  void close() {}
}

final _today = DateTime(2026, 9, 11);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<MethodCall> calls;
  late AlarmScheduler scheduler;
  var channelThrows = false;

  setUp(() {
    calls = <MethodCall>[];
    channelThrows = false;
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          if (channelThrows) throw PlatformException(code: 'no_platform');
          return null;
        });
    scheduler = AlarmScheduler(channel: channel);
  });

  Future<FreeDayPool> openPool() =>
      FreeDayPool.open(persistence: _MemPersistence(), deviceId: 'phone');

  List<String> lastCache() =>
      ((calls.last.arguments as Map)['dates'] as List).cast<String>();

  test("pushes the local pool and pulls a peer's day into it", () async {
    final remote = _MemRemote();
    // The PC marked a day, under its own device directory.
    final pcHlc = Hlc.newTick('pc');
    remote.files['${FreeDayPool.pathPrefix}/pc/${FreeDayPool.filename}'] =
        logToJson({
          '2026-09-20': Record(
            id: '2026-09-20',
            fields: {'state': ('free', pcHlc), 'consumed': (false, pcHlc)},
          ),
        });
    final pool = await openPool();
    await pool.mark(DateTime(2026, 9, 12), now: _today);

    final sync = FreeDaySync(
      openClient: () async => remote,
      scheduler: scheduler,
    );
    expect(await sync.sync(pool), 'Synced ✓');

    expect(pool.isFree(DateTime(2026, 9, 20)), isTrue, reason: 'pulled');
    final pushed =
        remote.files['${FreeDayPool.pathPrefix}/phone/${FreeDayPool.filename}'];
    expect(pushed, contains('2026-09-12'), reason: 'pushed');
    expect(calls.last.method, 'setFreeDays');
    expect(lastCache(), ['2026-09-12', '2026-09-20']);
  });

  test(
    'a device not connected to Firebase still refreshes the cache',
    () async {
      final pool = await openPool();
      await pool.mark(DateTime(2026, 9, 12), now: _today);
      final sync = FreeDaySync(
        openClient: () async => null,
        scheduler: scheduler,
      );
      expect(await sync.sync(pool), contains('connect Firebase'));
      expect(lastCache(), ['2026-09-12']);
    },
  );

  test('an unreachable remote reports an error and keeps the cache', () async {
    final pool = await openPool();
    await pool.mark(DateTime(2026, 9, 12), now: _today);
    final sync = FreeDaySync(
      openClient: () async => _Broken(),
      scheduler: scheduler,
    );
    expect(await sync.sync(pool), startsWith('Error:'));
    expect(pool.isFree(DateTime(2026, 9, 12)), isTrue);
    expect(lastCache(), ['2026-09-12']);
  });

  test('a client factory that throws is reported, not propagated', () async {
    final pool = await openPool();
    final sync = FreeDaySync(
      openClient: () async => throw StateError('keystore locked'),
      scheduler: scheduler,
    );
    expect(await sync.sync(pool), contains('keystore locked'));
    expect(calls.last.method, 'setFreeDays');
  });

  test('a missing platform channel does not fail the sync', () async {
    channelThrows = true;
    final pool = await openPool();
    final sync = FreeDaySync(
      openClient: () async => _MemRemote(),
      scheduler: scheduler,
    );
    expect(await sync.sync(pool), 'Synced ✓');
  });
}
