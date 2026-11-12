import 'dart:async';

import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/services/enforcement_bridge.dart';
import 'package:wake_alarm_sync/services/today_stakes.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/spoken_label.dart';
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
  ({DateTime by, DateTime lockThrough})? _stakes;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    ({DateTime by, DateTime lockThrough})? stakes;
    try {
      final state = await (widget.bridge ?? EnforcementBridge()).state();
      stakes = state == null ? null : ringStakes(state);
    } on Exception {
      stakes = null;
    }
    if (!mounted || stakes == null) return;
    setState(() => _stakes = stakes);
  }

  @override
  Widget build(BuildContext context) {
    final stakes = _stakes;
    if (stakes == null) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final statusColors = theme.extension<AppStatusColors>();
    final warningColor = statusColors?.warning ?? Colors.amber;
    final line =
        'Stick day: no dismiss by ${hhmm(stakes.by)} → apps locked through '
        '${formatDay(stakes.lockThrough)}';
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: SpokenLabel(
        semanticLabel: line,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.gavel_outlined, color: warningColor),
            const SizedBox(width: 4),
            Text(hhmm(stakes.by), style: TextStyle(color: warningColor)),
            const SizedBox(width: 4),
            const Icon(Icons.arrow_forward, size: 16),
            const SizedBox(width: 4),
            Icon(Icons.lock_outline, color: warningColor),
            const SizedBox(width: 4),
            Text(
              _formatLockDate(stakes.lockThrough),
              style: TextStyle(color: warningColor),
            ),
          ],
        ),
      ),
    );
  }

  String _formatLockDate(DateTime d) =>
      '${d.day.toString().padLeft(2, '0')}'
      '.${d.month.toString().padLeft(2, '0')}';
}
