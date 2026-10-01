import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/escape_dialog.dart';
import 'package:wake_alarm_sync/services/alarm_policy.dart';
import 'package:wake_alarm_sync/services/enforcement_bridge.dart';
import 'package:wake_alarm_sync/services/enforcement_state.dart';
import 'package:wake_alarm_sync/services/escape_hatch.dart';
import 'package:wake_alarm_sync/services/today_stakes.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// Today's stakes in plain words, anything already in force, the streak,
/// and the escape hatch while it lasts.
///
/// Self-loading from the native stick, keyed by the home screen's sync
/// epoch like the history card. Absent when the native side answers
/// nothing (a widget test, the desktop) rather than showing made-up stakes.
class StakesCard extends StatefulWidget {
  /// Creates the card; every dependency is injectable for tests.
  const StakesCard({
    super.key,
    this.bridge,
    this.hatch,
    this.now,
    this.nextAlarm,
    this.onEscaped,
    this.busy = false,
  });

  /// Native stick reader; defaults to the real channel.
  final EnforcementBridge? bridge;

  /// The escape hatch; defaults to the real one.
  final EscapeHatch? hatch;

  /// The clock; defaults to `DateTime.now`.
  final DateTime Function()? now;

  /// Tomorrow's alarm time; defaults to [AlarmPolicy.load].
  final Future<AlarmTime?> Function()? nextAlarm;

  /// Called after a successful escape, so the screen can publish it.
  final VoidCallback? onEscaped;

  /// Disables the escape while the screen is syncing.
  final bool busy;

  @override
  State<StakesCard> createState() => _StakesCardState();
}

class _StakesCardState extends State<StakesCard> {
  late final EnforcementBridge _bridge = widget.bridge ?? EnforcementBridge();
  late final EscapeHatch _hatch =
      widget.hatch ?? EscapeHatch(bridge: _bridge, now: widget.now);
  EnforcementState? _state;
  AlarmTime? _next;
  String _message = '';

  DateTime _now() => (widget.now ?? DateTime.now)();

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    EnforcementState? state;
    AlarmTime? next;
    try {
      state = await _bridge.state();
      next = await (widget.nextAlarm ?? () => _policyAlarm(_now()))();
    } on Exception {
      // No native side: show nothing rather than invented stakes.
    }
    if (!mounted) return;
    setState(() {
      _state = state;
      _next = next;
    });
  }

  /// Tomorrow's alarm as the policy will arm it (ramp + any one-shot
  /// override). Resolved from tomorrow's midnight: "the next alarm after
  /// now" would still be today's before it rings.
  static Future<AlarmTime?> _policyAlarm(DateTime now) async {
    final midnight = DateTime(now.year, now.month, now.day + 1);
    final policy = await AlarmPolicy.load(now: midnight);
    return (hour: policy.hour, minute: policy.minute);
  }

  Future<void> _escape() async {
    final reason = await showEscapeDialog(context);
    if (reason == null) return;
    final ok = await _hatch.use(reason);
    if (!mounted) return;
    setState(
      () => _message = ok
          ? 'Excused — lockdown lifted, publishing to the PC.'
          : 'The escape hatch refused (closed, or the reason is too short).',
    );
    await _load();
    if (ok) widget.onEscaped?.call();
  }

  @override
  Widget build(BuildContext context) {
    final state = _state;
    if (state == null) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final warning = theme.extension<AppStatusColors>()?.warning;
    final view = describeStakes(now: _now(), state: state, nextAlarm: _next);
    final body = theme.textTheme.bodyMedium;
    return Card(
      color: theme.colorScheme.surfaceContainerHigh,
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text(view.title, style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            for (final line in view.stakes)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Text(line, style: body),
              ),
            for (final line in view.pending)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Text(line, style: body?.copyWith(color: warning)),
              ),
            const SizedBox(height: 8),
            Text(
              view.streak,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            if (_message.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(_message, style: body),
            ],
            if (_hatch.isOpen) ...[
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: widget.busy ? null : () => unawaited(_escape()),
                  icon: const Icon(Icons.bug_report_outlined),
                  label: const Text('That was a bug'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
