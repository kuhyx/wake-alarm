/// Tests for cues.dart: CueKind classifier and StatusCue rendering.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/ui/cues.dart';

void main() {
  group('cueKindOf', () {
    test('empty returns null', () => expect(cueKindOf(''), isNull));

    test('busy ellipsis', () {
      expect(cueKindOf('Syncing…'), equals(CueKind.busy));
      expect(cueKindOf('Syncing...'), equals(CueKind.busy));
    });

    test('error keywords', () {
      const cases = [
        'Error: x',
        'Could not connect',
        'Service unavailable',
        'Connection refused',
        'Not found',
        'Unknown error',
        'Too early to dismiss',
        'not earlier than 07:00',
        'Wrong tag',
        'Failed to sync',
        'Walk too short',
      ];
      for (final c in cases) {
        expect(cueKindOf(c), equals(CueKind.error), reason: c);
      }
    });

    test('ok keywords', () {
      const cases = [
        'Synced ✓',
        'Connected to GitHub',
        'Tag registered',
        'Tag matched',
        'Captured photo',
        'Synced',
        'Alarm Armed',
        'Done',
        'Correct answer',
        'Dismissed',
        'Excused day',
      ];
      for (final c in cases) {
        expect(cueKindOf(c), equals(CueKind.ok), reason: c);
      }
    });

    test('warning keywords', () {
      expect(
        cueKindOf('Connect a sync backend in Settings first.'),
        equals(CueKind.warning),
      );
      expect(cueKindOf('Open Settings to connect'), equals(CueKind.warning));
    });

    test('default info', () {
      expect(cueKindOf('hello'), equals(CueKind.info));
      expect(cueKindOf('Syncing now'), equals(CueKind.info));
    });
  });

  group('StatusCue', () {
    testWidgets('renders no Text', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: StatusCue(semanticLabel: 'Error: x')),
        ),
      );
      expect(find.byType(Text), findsNothing);
    });

    testWidgets('renders error icon for error kind', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: StatusCue(semanticLabel: 'Error: x')),
        ),
      );
      expect(find.byIcon(Icons.error_outline), findsOneWidget);
    });

    testWidgets('renders CircularProgressIndicator for busy', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: StatusCue(semanticLabel: 'Syncing…')),
        ),
      );
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('renders SizedBox.shrink for empty label', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: StatusCue(semanticLabel: '')),
        ),
      );
      expect(find.byType(Icon), findsNothing);
      expect(find.byType(CircularProgressIndicator), findsNothing);
    });

    testWidgets('semanticLabel is reachable via semantics', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: StatusCue(semanticLabel: 'Error: connection failed'),
          ),
        ),
      );

      final handle = tester.ensureSemantics();
      try {
        final semanticsFinder = find.byWidgetPredicate(
          (widget) =>
              widget is Semantics &&
              widget.properties.label?.contains('connection failed') == true,
        );
        final semantics = tester.getSemantics(semanticsFinder);
        expect(semantics.label, contains('connection failed'));
      } finally {
        handle.dispose();
      }
    });

    testWidgets('SpokenLabel wraps child with semantics label', (tester) async {
      const label = 'Close button';
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: SpokenLabel(semanticLabel: label, child: Icon(Icons.close)),
          ),
        ),
      );

      final handle = tester.ensureSemantics();
      try {
        final semantics = tester.getSemantics(find.byType(SpokenLabel));
        expect(semantics.label, equals(label));
      } finally {
        handle.dispose();
      }
    });
  });
}
