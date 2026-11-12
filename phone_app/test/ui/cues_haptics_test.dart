/// Tests for cues.dart: haptic feedback and semantics behavior.
library;

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/ui/cues.dart';

void main() {
  group('StatusCue haptics', () {
    testWidgets('error triggers heavyImpact haptic', (tester) async {
      final calls = <MethodCall>[];
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (call) async {
          calls.add(call);
          return null;
        },
      );

      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: StatusCue(semanticLabel: 'Error: x')),
        ),
      );

      expect(calls, isNotEmpty);
      final heavyCalls = calls.where(
        (c) =>
            c.method == 'HapticFeedback.vibrate' &&
            c.arguments == 'HapticFeedbackType.heavyImpact',
      );
      expect(heavyCalls, isNotEmpty);
    });

    testWidgets('ok triggers lightImpact on kind change', (tester) async {
      final calls = <MethodCall>[];
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (call) async {
          calls.add(call);
          return null;
        },
      );

      var currentKind = CueKind.info;
      var currentLabel = 'Syncing';

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: StatefulBuilder(
              builder: (context, setState) {
                return Column(
                  children: [
                    StatusCue(semanticLabel: currentLabel, kind: currentKind),
                    TextButton(
                      onPressed: () {
                        setState(() {
                          currentKind = CueKind.ok;
                          currentLabel = 'Synced ✓';
                        });
                      },
                      child: const Text('Change'),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
      );
      calls.clear();

      await tester.tap(find.byType(TextButton));
      await tester.pump();

      final lightCalls = calls.where(
        (c) =>
            c.method == 'HapticFeedback.vibrate' &&
            c.arguments == 'HapticFeedbackType.lightImpact',
      );
      expect(lightCalls, isNotEmpty);
    });

    void expectHeavyCalls(int expected, List<MethodCall> calls) {
      final count = calls
          .where(
            (c) =>
                c.method == 'HapticFeedback.vibrate' &&
                c.arguments == 'HapticFeedbackType.heavyImpact',
          )
          .length;
      expect(count, equals(expected));
    }

    testWidgets('haptic fires once on MediaQuery change with same error kind', (
      tester,
    ) async {
      final calls = <MethodCall>[];
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (call) async {
          calls.add(call);
          return null;
        },
      );

      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: StatusCue(semanticLabel: 'Error: x')),
        ),
      );
      calls.clear();

      // Pump again inside a MediaQuery with different viewInsets
      await tester.pumpWidget(
        const MaterialApp(
          home: MediaQuery(
            data: MediaQueryData(viewInsets: EdgeInsets.only(bottom: 300)),
            child: Scaffold(body: StatusCue(semanticLabel: 'Error: x')),
          ),
        ),
      );

      // Should NOT fire again - same error kind, same label
      expectHeavyCalls(1, calls);
    });

    testWidgets(
      'haptic fires again when semanticLabel changes with same error kind',
      (tester) async {
        final calls = <MethodCall>[];
        tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
          SystemChannels.platform,
          (call) async {
            calls.add(call);
            return null;
          },
        );

        // Initial pump with error cue
        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(body: StatusCue(semanticLabel: 'Error: first')),
          ),
        );
        calls.clear();

        // Pump with different semanticLabel but same error kind
        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(body: StatusCue(semanticLabel: 'Error: second')),
          ),
        );

        // Should fire again because semanticLabel changed
        expectHeavyCalls(1, calls);
      },
    );
  });
}
