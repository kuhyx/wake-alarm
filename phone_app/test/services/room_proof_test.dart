import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/room_proof.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late AlarmScheduler scheduler;
  var steps = 0;

  setUp(() {
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'stepCount') return steps;
          return null;
        });
    scheduler = AlarmScheduler(channel: channel);
  });

  group('NFC', () {
    test('a matching registered tag satisfies the proof', () {
      final proof = RoomProof(scheduler: scheduler, registeredTagId: 'tag-1');
      final result = proof.checkNfc('tag-1');
      expect(result.satisfied, isTrue);
      expect(result.kind, RoomProofKind.nfc);
    });

    test('a different tag does not', () {
      final proof = RoomProof(scheduler: scheduler, registeredTagId: 'tag-1');
      expect(proof.checkNfc('tag-2').satisfied, isFalse);
    });

    test('no registered tag means NFC cannot satisfy, not that all pass', () {
      final proof = RoomProof(scheduler: scheduler);
      final result = proof.checkNfc('tag-1');
      expect(result.satisfied, isFalse);
      expect(result.detail, contains('No NFC tag registered'));
    });

    test('an empty registered tag is treated as unregistered', () {
      final proof = RoomProof(scheduler: scheduler, registeredTagId: '');
      expect(proof.checkNfc('').satisfied, isFalse);
    });
  });

  group('QR', () {
    test('the expected payload satisfies the proof', () {
      final proof = RoomProof(scheduler: scheduler);
      final result = proof.checkQr('kitchen', expected: 'kitchen');
      expect(result.satisfied, isTrue);
      expect(result.kind, RoomProofKind.qr);
    });

    test('a different payload does not', () {
      final proof = RoomProof(scheduler: scheduler);
      expect(proof.checkQr('bedroom', expected: 'kitchen').satisfied, isFalse);
    });

    test('an empty expectation never matches', () {
      final proof = RoomProof(scheduler: scheduler);
      expect(proof.checkQr('', expected: '').satisfied, isFalse);
    });
  });

  group('steps fallback', () {
    test('reports the sensor being unavailable', () async {
      steps = -1;
      final proof = RoomProof(scheduler: scheduler);
      final result = await proof.checkSteps(const Duration(minutes: 5));
      expect(result.satisfied, isFalse);
      expect(result.detail, contains('unavailable'));
    });

    test('too few steps does not satisfy', () async {
      steps = 5;
      final proof = RoomProof(scheduler: scheduler);
      final result = await proof.checkSteps(const Duration(minutes: 5));
      expect(result.satisfied, isFalse);
      expect(result.detail, contains('5/${RoomProof.requiredSteps}'));
    });

    test('enough steps but too little time does not satisfy', () async {
      // This is the shake-it-in-bed case the elapsed requirement exists for.
      steps = RoomProof.requiredSteps + 10;
      final proof = RoomProof(scheduler: scheduler);
      final result = await proof.checkSteps(const Duration(seconds: 10));
      expect(result.satisfied, isFalse);
      expect(result.detail, contains('Keep moving'));
    });

    test('enough steps and enough time satisfies', () async {
      steps = RoomProof.requiredSteps;
      final proof = RoomProof(scheduler: scheduler);
      final result = await proof.checkSteps(RoomProof.requiredElapsed);
      expect(result.satisfied, isTrue);
      expect(result.kind, RoomProofKind.steps);
    });
  });
}
