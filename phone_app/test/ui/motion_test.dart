/// Tests for the motion tokens and the app route.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/ui/motion_route.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

Future<Duration> _routeDuration(WidgetTester t, {required bool off}) async {
  late Duration d;
  await t.pumpWidget(
    MediaQuery(
      data: MediaQueryData(disableAnimations: off),
      child: Builder(
        builder: (context) {
          d = appRoute<void>(
            context,
            (_) => const SizedBox(),
          ).transitionDuration;
          return const SizedBox();
        },
      ),
    ),
  );
  return d;
}

void main() {
  test('duration tokens match DOCS-motion', () {
    expect(MotionDuration.instant, Duration.zero);
    expect(MotionDuration.fast, const Duration(milliseconds: 120));
    expect(MotionDuration.base, const Duration(milliseconds: 200));
    expect(MotionDuration.slow, const Duration(milliseconds: 320));
  });

  test('curves match DOCS-motion', () {
    expect(MotionCurve.decelerate, const Cubic(0, 0, 0, 1));
    expect(MotionCurve.accelerate, const Cubic(0.3, 0, 1, 1));
    expect(MotionCurve.standard, const Cubic(0.2, 0, 0, 1));
  });

  testWidgets('route is slow, instant under disableAnimations', (t) async {
    expect(await _routeDuration(t, off: false), MotionDuration.slow);
    expect(await _routeDuration(t, off: true), Duration.zero);
  });
}
