import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/weight_entry.dart';

/// How many mornings the home screen shows.
const int kHistoryShown = 7;

/// The last week of mornings: outcome, re-rings and weight, one line each.
///
/// Self-loading, keyed by the home screen's sync epoch so a history a pull
/// just restored appears without a cold start. Absent entirely until the
/// first session has finished — an empty card would only say "not yet".
class HomeHistoryCard extends StatefulWidget {
  /// Creates the card; [store] is injectable for tests.
  const HomeHistoryCard({super.key, this.store});

  /// Session persistence; defaults to SharedPreferences.
  final SessionStore? store;

  @override
  State<HomeHistoryCard> createState() => _HomeHistoryCardState();
}

class _HomeHistoryCardState extends State<HomeHistoryCard> {
  List<MorningSession> _sessions = const <MorningSession>[];

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    final history = await (widget.store ?? SessionStore()).history();
    if (!mounted) return;
    setState(() => _sessions = history.take(kHistoryShown).toList());
  }

  @override
  Widget build(BuildContext context) {
    if (_sessions.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text('Last mornings', style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),
        for (var i = 0; i < _sessions.length; i++)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Text(
              describeMorning(_sessions[i], previousWeight: _previousWeight(i)),
              style: theme.textTheme.bodyMedium,
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
      final delta = kg - previousWeight;
      final sign = delta > 0 ? '+' : (delta < 0 ? '−' : '±');
      weight += ' ($sign${delta.abs().toStringAsFixed(1)})';
    }
  }
  final energy = session.energy == null
      ? ''
      : ' · energy ${session.energy}/$maxEnergy';
  return '${session.date.substring(5)} $mark $rings$weight$energy';
}
