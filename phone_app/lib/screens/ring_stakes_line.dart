import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/enforcement_bridge.dart';
import 'package:wake_alarm_sync/services/today_stakes.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// The ring screen's one line: what not dismissing costs today.
///
/// Read once from the native stick when the ring opens, so the time and the
/// lockdown date are the ones the native check will actually use. Absent on
/// a day with no stick-day consequence, and whenever the platform answers
/// nothing -- it must never be what breaks a ring.
class RingStakesLine extends StatefulWidget {
  /// Creates the line; [bridge] is injectable for tests.
  const RingStakesLine({super.key, this.bridge});

  /// Native stick reader; defaults to the real channel.
  final EnforcementBridge? bridge;

  @override
  State<RingStakesLine> createState() => _RingStakesLineState();
}

class _RingStakesLineState extends State<RingStakesLine> {
  String? _line;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    String? line;
    try {
      final state = await (widget.bridge ?? EnforcementBridge()).state();
      line = state == null ? null : ringStakesLine(state);
    } on Exception {
      line = null;
    }
    if (!mounted || line == null) return;
    setState(() => _line = line);
  }

  @override
  Widget build(BuildContext context) {
    final line = _line;
    if (line == null) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Text(
        line,
        textAlign: TextAlign.center,
        style: theme.textTheme.bodyMedium?.copyWith(
          // Null-safe: a missing theme extension must not break a ring.
          color: theme.extension<AppStatusColors>()?.warning,
        ),
      ),
    );
  }
}
