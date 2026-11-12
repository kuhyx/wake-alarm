import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/screens/home_presence_line.dart';
import 'package:wake_alarm_sync/screens/home_tiles.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// The home screen's body: the armed time, the earlier-only control and the
/// status line.
///
/// Split out of `home_screen.dart` for the 250-line cap. Deliberately
/// stateless, taking plain values -- the screen keeps the state and the
/// ordering rules, which is where the bugs lived.
class HomeBody extends StatelessWidget {
  /// Creates the body from already-resolved state.
  const HomeBody({
    required this.time,
    required this.baseline,
    required this.isOverridden,
    required this.busy,
    required this.status,
    required this.configured,
    required this.onPickEarlier,
    this.syncEpoch = 0,
    this.onEscaped,
    super.key,
  });

  /// The armed time, preformatted.
  final String time;

  /// The baseline time, shown while an override is active.
  final String baseline;

  /// Whether a one-shot earlier start is in force.
  final bool isOverridden;

  /// Whether an operation is in flight.
  final bool busy;

  /// The status line; may be a raw exception string.
  final String status;

  /// Whether a sync backend is connected.
  final bool configured;

  /// Called when the user asks to wake earlier tomorrow.
  final VoidCallback onPickEarlier;

  /// Bumped after every sync so the presence line re-reads the home location
  /// a pull may just have restored, instead of showing the pre-sync verdict
  /// until the next cold start.
  final int syncEpoch;

  /// Called after the escape hatch was used, so the screen publishes it.
  final VoidCallback? onEscaped;

  IconData? _statusIcon(String status) {
    if (status.startsWith('Connect a sync backend')) return Icons.cloud_off;
    if (status.startsWith('Sync store unavailable')) return Icons.sync_problem;
    if (status.contains('✓')) return Icons.cloud_done;
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      // Fits one screen: stakes and history sit behind tiles. The scroll view
      // is only the landscape safety net (~360px of body height); in portrait
      // its extent is 0, which `home_fit_test.dart` asserts.
      child: LayoutBuilder(
        builder: (context, box) => SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: box.maxHeight - 48),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.alarm_on,
                    size: 32,
                    color: theme.colorScheme.primary,
                    semanticLabel: 'Alarm is armed for',
                  ),
                  HomePresenceLine(key: ValueKey<int>(syncEpoch)),
                  const SizedBox(height: 16),
                  Text(
                    time,
                    style: theme.textTheme.displayLarge?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 8),
                  if (isOverridden)
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.restore,
                          size: 18,
                          semanticLabel:
                              'One-shot early start, back to $baseline '
                              'after it rings',
                        ),
                        Text(baseline),
                      ],
                    )
                  else
                    Icon(
                      Icons.all_inclusive,
                      size: 18,
                      color: theme.colorScheme.onSurfaceVariant,
                      semanticLabel: 'Every day. It cannot be turned off.',
                    ),
                  const SizedBox(height: 32),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton(
                      onPressed: busy ? null : onPickEarlier,
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                      child: const Icon(
                        Icons.arrow_upward,
                        semanticLabel: 'Wake me earlier tomorrow',
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  if (status.isNotEmpty) ...[
                    StatusCue(semanticLabel: status, icon: _statusIcon(status)),
                    const SizedBox(height: 24),
                  ],
                  HomeTiles(
                    syncEpoch: syncEpoch,
                    busy: busy,
                    onEscaped: onEscaped,
                  ),
                  if (!configured) ...[
                    const SizedBox(height: 16),
                    Icon(
                      Icons.cloud_off,
                      size: 28,
                      color: theme.extension<AppStatusColors>()!.warning,
                      semanticLabel: 'Open Settings to connect Firebase',
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
