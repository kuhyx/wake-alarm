/// Text-free status cue widgets: enum classifier, semantic icon with haptic
/// feedback, and spoken-only label wrapper.
library;

import 'dart:async' show unawaited;
import 'dart:math' show pi, sin;

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/ui/theme.dart' show AppStatusColors;

export 'package:wake_alarm_sync/ui/spoken_label.dart';

/// Semantic kind for a status cue; drives icon, colour and haptic.
enum CueKind {
  /// Busy/loading state.
  busy,

  /// Success/connected state.
  ok,

  /// Error/failed state.
  error,

  /// Warning/caution state.
  warning,

  /// Informational state (default).
  info,
}

/// Classifies a status sentence into a [CueKind].
///
/// Uses the app's existing colour conventions (e.g.
/// `status.contains('Error')`). Returns `null` for empty string.
CueKind? cueKindOf(String status) {
  if (status.isEmpty) return null;
  if (status.endsWith('…') || status.endsWith('...')) return CueKind.busy;

  const errorKeywords = [
    'Error',
    'Could not',
    'unavailable',
    'refused',
    'Not ',
    'Unknown',
    'Too early',
    'not earlier',
    'Wrong',
    'Failed',
    'too short',
  ];
  for (final kw in errorKeywords) {
    if (status.contains(kw)) return CueKind.error;
  }

  const okKeywords = [
    '✓',
    'Connected',
    'registered',
    'matched',
    'Captured',
    'Synced',
    'Armed',
    'Done',
    'Correct',
    'Dismissed',
    'Excused',
  ];
  for (final kw in okKeywords) {
    if (status.contains(kw)) return CueKind.ok;
  }

  if (status.contains('Connect a sync backend') ||
      status.contains('Open Settings')) {
    return CueKind.warning;
  }
  return CueKind.info;
}

/// A semantic status icon with haptic feedback and a shake animation on error.
///
/// Paints no text. Icon and colour derived from [kind] (defaulting to
/// [cueKindOf] of [semanticLabel]). Renders [SizedBox.shrink] when [kind]
/// resolves to `null` (empty label).
class StatusCue extends StatefulWidget {
  /// Creates a status cue.
  ///
  /// [semanticLabel] is the spoken label (also used to infer [kind] when
  /// not provided). [kind] overrides inference. [icon] overrides the default
  /// icon for the kind. [size] controls the icon/spinner dimension.
  const StatusCue({
    required this.semanticLabel,
    this.kind,
    this.icon,
    this.size = 28,
    super.key,
  });

  /// The spoken label; also used to infer the cue kind when [kind] is null.
  final String semanticLabel;

  /// Explicit kind override; defaults to [cueKindOf(semanticLabel)].
  final CueKind? kind;

  /// Optional icon override.
  final IconData? icon;

  /// Icon / spinner dimension.
  final double size;

  /// The resolved kind (explicit or inferred).
  CueKind? get resolvedKind => kind ?? cueKindOf(semanticLabel);

  @override
  State<StatusCue> createState() => _StatusCueState();
}

class _StatusCueState extends State<StatusCue>
    with SingleTickerProviderStateMixin {
  late final AnimationController _shakeCtrl;
  late final Animation<double> _shakeAnim;
  CueKind? _prevKind;
  bool _shown = false;

  @override
  void initState() {
    super.initState();
    _shakeCtrl = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _shakeAnim = Tween<double>(
      begin: 0,
      end: 1,
    ).animate(CurvedAnimation(parent: _shakeCtrl, curve: Curves.easeOut));
    _prevKind = widget.resolvedKind;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_shown) {
      _shown = true;
      _maybeTriggerHaptic(_prevKind);
    }
  }

  @override
  void didUpdateWidget(covariant StatusCue oldWidget) {
    super.didUpdateWidget(oldWidget);
    final newKind = widget.resolvedKind;
    final labelChanged = oldWidget.semanticLabel != widget.semanticLabel;
    if (newKind != _prevKind || labelChanged) {
      _maybeTriggerHaptic(newKind);
      _prevKind = newKind;
    }
  }

  void _maybeTriggerHaptic(CueKind? kind) {
    if (kind == null) return;
    final disableAnim = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    switch (kind) {
      case CueKind.error:
        unawaited(HapticFeedback.heavyImpact());
        if (!disableAnim) _shakeCtrl.forward(from: 0);
      case CueKind.ok:
        unawaited(HapticFeedback.lightImpact());
      case CueKind.busy:
      case CueKind.warning:
      case CueKind.info:
    }
  }

  @override
  void dispose() {
    _shakeCtrl.dispose();
    super.dispose();
  }

  Widget _buildSemantics(Widget child) {
    return Semantics(
      liveRegion: true,
      label: widget.semanticLabel,
      child: ExcludeSemantics(child: child),
    );
  }

  @override
  Widget build(BuildContext context) {
    final kind = widget.resolvedKind;
    if (kind == null) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final statusColors = theme.extension<AppStatusColors>();
    final colorScheme = theme.colorScheme;

    final iconData =
        widget.icon ??
        switch (kind) {
          CueKind.ok => Icons.check_circle,
          CueKind.error => Icons.error_outline,
          CueKind.warning => Icons.warning_amber_rounded,
          CueKind.info => Icons.info_outline,
          CueKind.busy => Icons.sync,
        };

    final color = switch (kind) {
      CueKind.ok => statusColors?.success ?? Colors.green,
      CueKind.error => colorScheme.error,
      CueKind.warning => statusColors?.warning ?? Colors.amber,
      CueKind.info => colorScheme.onSurfaceVariant,
      CueKind.busy => colorScheme.primary,
    };

    late final Widget child;
    switch (kind) {
      case CueKind.busy:
        child = const SizedBox.square(
          dimension: 28,
          child: CircularProgressIndicator(strokeWidth: 3),
        );
      case CueKind.ok:
      case CueKind.error:
      case CueKind.warning:
      case CueKind.info:
        child = Icon(iconData, size: widget.size, color: color);
    }

    if (kind == CueKind.error) {
      return AnimatedBuilder(
        animation: _shakeAnim,
        builder: (context, _) => Transform.translate(
          offset: Offset(sin(_shakeAnim.value * 3 * 2 * pi) * 6, 0),
          child: _buildSemantics(child),
        ),
      );
    }
    return _buildSemantics(child);
  }
}
