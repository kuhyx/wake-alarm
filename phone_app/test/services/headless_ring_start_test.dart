import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/headless_ring_start.dart';
import 'package:wake_alarm_sync/services/ring_start_recorder.dart';

/// Records calls; optionally throws, to prove `done` is still sent.
class _Recorder extends RingStartRecorder {
  _Recorder({this.fail = false});

  final bool fail;
  int calls = 0;

  @override
  Future<bool> record() async {
    calls++;
    if (fail) throw StateError('boom');
    return true;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel(headlessChannelName);
  late List<String> calls;

  setUp(() {
    calls = <String>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call.method);
          return null;
        });
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null),
    );
  });

  test('records once, then tells the native side it is done', () async {
    final recorder = _Recorder();
    await runHeadlessRingStart(recorder: recorder);
    expect(recorder.calls, 1);
    expect(calls, ['done']);
  });

  test('done is sent even when recording blows up', () async {
    await expectLater(
      runHeadlessRingStart(recorder: _Recorder(fail: true)),
      throwsStateError,
    );
    expect(calls, ['done']);
  });

  test('an unanswered done is swallowed', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
    await runHeadlessRingStart(recorder: _Recorder());
  });
}
