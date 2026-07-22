/// The app's design tokens: one identical palette shared across every one
/// of kuhy's apps (Flutter, web, Python/Tkinter alike) — see the
/// `unified-design-system` skill (`~/.claude/skills/unified-design-system/`)
/// for the frozen token table this file implements. Built from an explicit
/// `ColorScheme`, not `ColorScheme.fromSeed`, because the shared palette is
/// hand-picked, not algorithmically derived from one seed color.
library;

import 'package:flutter/material.dart';

/// Builds the app's single dark `ThemeData` from the shared token set.
ThemeData buildAppTheme() {
  const colorScheme = ColorScheme.dark(
    surface: Color(0xFF211D1B), // ink
    surfaceContainerHighest: Color(0xFF38312E), // ink-raised-2
    surfaceContainerHigh: Color(0xFF2B2624), // ink-raised-1
    onSurface: Color(0xFFECEAE9), // text-on-dark
    onSurfaceVariant: Color(0xFFAAA09A), // muted-on-dark
    outline: Color(0xFF463E3A), // line-dark
    primary: Color(0xFFB8862E), // accent
    onPrimary: Color(0xFF211D1B), // on-fill — filled surfaces use dark text
    // secondary/tertiary mirror primary — the shared palette has one accent,
    // not a separate secondary hue. Leaving these undefined lets Flutter
    // fall back to stock Material teal on any widget that reaches for
    // secondaryContainer (Chip, SegmentedButton, etc.) — confirmed as a
    // real, live bug on two other apps sharing this template.
    secondary: Color(0xFFB8862E),
    onSecondary: Color(0xFF211D1B),
    secondaryContainer: Color(0xFF463E3A),
    onSecondaryContainer: Color(0xFFB8862E),
    tertiary: Color(0xFFB8862E),
    onTertiary: Color(0xFF211D1B),
    tertiaryContainer: Color(0xFF463E3A),
    onTertiaryContainer: Color(0xFFB8862E),
    error: Color(0xFFE2585F), // danger
    onError: Color(0xFF211D1B), // on-fill
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: colorScheme,
    scaffoldBackgroundColor: colorScheme.surface,
    extensions: const [AppStatusColors.dark],
    // No custom shadow/elevation exists elsewhere in this app — the one
    // Card (_StatusCard) is the sole place M3's default elevation would
    // otherwise introduce a shadow in an all-dark UI (rule 26).
    cardTheme: const CardThemeData(elevation: 0),
  );
}

/// Semantic status colors M3's [ColorScheme] has no role for (it only has
/// `error`). Used instead of the ad hoc `Colors.greenAccent`/`Colors.orange`
/// literals previously scattered across both screens.
@immutable
class AppStatusColors extends ThemeExtension<AppStatusColors> {
  /// Creates a status-color set.
  const AppStatusColors({required this.success, required this.warning});

  /// The shared dark-theme instance — success/warning from the unified
  /// palette (danger already exists as `colorScheme.error`).
  static const dark = AppStatusColors(
    success: Color(0xFF8A9A3C),
    warning: Color(0xFFE0A63C),
  );

  /// Positive/connected status (e.g. "Connected to GitHub").
  final Color success;

  /// Caution/pending status (e.g. "Open Settings to connect GitHub").
  final Color warning;

  @override
  AppStatusColors copyWith({Color? success, Color? warning}) =>
      AppStatusColors(
        success: success ?? this.success,
        warning: warning ?? this.warning,
      );

  @override
  AppStatusColors lerp(AppStatusColors? other, double t) {
    if (other is! AppStatusColors) return this;
    return AppStatusColors(
      success: Color.lerp(success, other.success, t) ?? success,
      warning: Color.lerp(warning, other.warning, t) ?? warning,
    );
  }
}
