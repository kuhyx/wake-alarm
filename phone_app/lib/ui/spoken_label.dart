/// A wrapper that provides a spoken label for accessibility without any
/// visible text (no Tooltip).
///
/// Use for icon-only controls whose wording must remain only for TalkBack.
library;

import 'package:material_ui/material_ui.dart';

/// A wrapper that provides a spoken label for accessibility without any
/// visible text (no Tooltip).
///
/// Use for icon-only controls whose wording must remain only for TalkBack.
class SpokenLabel extends StatelessWidget {
  /// Creates a spoken label wrapper.
  const SpokenLabel({
    required this.semanticLabel,
    required this.child,
    super.key,
  });

  /// The accessibility label.
  final String semanticLabel;

  /// The child widget to wrap.
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: semanticLabel,
      child: ExcludeSemantics(child: child),
    );
  }
}
