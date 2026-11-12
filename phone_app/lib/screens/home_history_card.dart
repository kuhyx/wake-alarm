import 'dart:async';

import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/weight_entry.dart';
import 'package:wake_alarm_sync/ui/dashed_slot.dart';
import 'package:wake_alarm_sync/ui/spoken_label.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// How many mornings the home screen shows.
const int kHistoryShown = 7;

/// The last week of mornings: outcome, re-rings and weight, one line each.
///
/// Self-loading, keyed by the home screen's sync epoch so a history a pull
/// just restored appears without a cold start. Absent entirely until the
/// first session has finished — an empty card would only say "not yet".
class HomeHistoryCard extends StatefulWidget {
  /// Creates the card; [store] is injectable for tests.
  const HomeHistoryCard({super.key, this.store, this.emptyText});

  /// Session persistence; defaults to SharedPreferences.
  final SessionStore? store;

  /// Shown once loading found no finished morning, instead of nothing. The
  /// home screen opens this card from a tile, so a blank sheet needs a
  /// sentence.
  final String? emptyText;

  @override
  State<HomeHistoryCard> createState() => _HomeHistoryCardState();
}

class _HomeHistoryCardState extends State<HomeHistoryCard> {
  List<MorningSession> _sessions = const <MorningSession>[];
  bool _loaded = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    final history = await (widget.store ?? SessionStore()).history();
    if (!mounted) return;
    setState(() {
      _sessions = history.take(kHistoryShown).toList();
      _loaded = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_sessions.isEmpty) {
      final empty = widget.emptyText;
      return _loaded && empty != null
          ? SpokenLabel(semanticLabel: empty, child: const DashedSlot())
          : const SizedBox.shrink();
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        for (var i = 0; i < _sessions.length; i++)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: _MorningRow(
              key: ValueKey<String>('history-${_sessions[i].date}'),
              session: _sessions[i],
              previousWeight: _previousWeight(i),
            ),
          ),
      ],
    );
  }

  /// The nearest older weigh-in, for the delta.
  double? _previousWeight(int index) {
    for (var i = index + 1; i < _sessions.length; i++) {
      final kg = _sessions[i].weightKg;
      if (kg != null) return kg;
    }
    return null;
  }
}

/// One morning as glyphs and numbers; [describeMorning] is its spoken form.
class _MorningRow extends StatelessWidget {
  const _MorningRow({
    required this.session,
    required this.previousWeight,
    super.key,
  });

  final MorningSession session;
  final double? previousWeight;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final status = theme.extension<AppStatusColors>();
    final muted = theme.colorScheme.onSurfaceVariant;
    final (IconData outcome, Color colour) = switch (session.outcome) {
      SessionOutcome.completed => (
        Icons.check_circle,
        status?.success ?? Colors.green,
      ),
      SessionOutcome.failed => (Icons.cancel, theme.colorScheme.error),
      SessionOutcome.active => (Icons.more_horiz, muted),
    };
    final kg = session.weightKg;
    final previous = previousWeight;
    final energy = session.energy;
    return SpokenLabel(
      semanticLabel: describeMorning(session, previousWeight: previous),
      // Wrap, not Row: a long weight delta must not overflow a narrow sheet.
      child: Wrap(
        crossAxisAlignment: WrapCrossAlignment.center,
        children: <Widget>[
          Text(session.date.substring(5)),
          const SizedBox(width: 8),
          Icon(outcome, color: colour, size: 20),
          const SizedBox(width: 12),
          Icon(Icons.replay, size: 16, color: muted),
          Text('${session.reRings}'),
          if (kg != null) ...<Widget>[
            const SizedBox(width: 12),
            Icon(Icons.monitor_weight_outlined, size: 16, color: muted),
            Text('$kg'),
            if (previous != null) Text(' (${_signed(kg - previous)})'),
          ],
          if (energy != null) ...<Widget>[
            const SizedBox(width: 12),
            Icon(Icons.bolt, size: 16, color: muted),
            Text('$energy/$maxEnergy'),
          ],
        ],
      ),
    );
  }
}

String _signed(double delta) {
  final sign = delta > 0 ? '+' : (delta < 0 ? '−' : '±');
  return '$sign${delta.abs().toStringAsFixed(1)}';
}

/// One line for [session]: `09-16 ✓ 0 re-rings · 72.4 kg (−0.3) · energy 3/5`.
String describeMorning(MorningSession session, {double? previousWeight}) {
  final mark = switch (session.outcome) {
    SessionOutcome.completed => '✓',
    SessionOutcome.failed => '✗',
    SessionOutcome.active => '…',
  };
  final rings = '${session.reRings} re-ring${session.reRings == 1 ? '' : 's'}';
  final kg = session.weightKg;
  var weight = '';
  if (kg != null) {
    weight = ' · $kg kg';
    if (previousWeight != null) {
      weight += ' (${_signed(kg - previousWeight)})';
    }
  }
  final energy = session.energy == null
      ? ''
      : ' · energy ${session.energy}/$maxEnergy';
  return '${session.date.substring(5)} $mark $rings$weight$energy';
}
