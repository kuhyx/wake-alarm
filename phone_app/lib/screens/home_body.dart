import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/home_presence_line.dart';
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

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Alarm is armed for', style: TextStyle(fontSize: 16)),
              HomePresenceLine(key: ValueKey<int>(syncEpoch)),
              const SizedBox(height: 16),
              Text(
                time,
                style: Theme.of(
                  context,
                ).textTheme.displayLarge?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text(
                isOverridden
                    ? 'One-shot early start — back to $baseline '
                          'after it rings'
                    : 'Every day. It cannot be turned off.',
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 13),
              ),
              const SizedBox(height: 32),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: busy ? null : onPickEarlier,
                  icon: const Icon(Icons.arrow_upward),
                  label: const Text('Wake me earlier tomorrow'),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                ),
              ),
              const SizedBox(height: 24),
              if (status.isNotEmpty)
                Text(
                  status,
                  textAlign: TextAlign.center,
                  // Bounded: status can be a raw `'Error: $e'`, i.e. an
                  // arbitrarily long exception toString(). Unbounded, that
                  // alone added 100-150px and pushed this column past the
                  // viewport even in portrait. The scroll view above makes
                  // the overflow recoverable; this keeps it from happening.
                  maxLines: 4,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: status.contains('Error')
                        ? Theme.of(context).colorScheme.error
                        : Theme.of(
                            context,
                          ).extension<AppStatusColors>()!.success,
                  ),
                ),
              if (!configured) ...[
                const SizedBox(height: 16),
                Text(
                  'Open Settings (gear icon) to connect Firebase.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Theme.of(
                      context,
                    ).extension<AppStatusColors>()!.warning,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
