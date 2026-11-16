/// The app's one page route: slow slide, decelerate in, accelerate out.
library;

import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// A route to [builder]'s page using the shared motion tokens; instant under
/// the OS "Remove animations" setting.
PageRoute<T> appRoute<T>(BuildContext context, WidgetBuilder builder) {
  final duration = motionDuration(context, MotionDuration.slow);
  return PageRouteBuilder<T>(
    transitionDuration: duration,
    reverseTransitionDuration: duration,
    pageBuilder: (context, _, _) => builder(context),
    transitionsBuilder: (context, animation, secondary, child) {
      final slide = Tween<Offset>(begin: const Offset(1, 0), end: Offset.zero)
          .animate(
            CurvedAnimation(
              parent: animation,
              curve: MotionCurve.decelerate,
              reverseCurve: MotionCurve.accelerate,
            ),
          );
      return SlideTransition(position: slide, child: child);
    },
  );
}
