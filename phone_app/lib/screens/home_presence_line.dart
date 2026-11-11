import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/home_presence.dart';
import 'package:wake_alarm_sync/ui/cues.dart';

/// One line saying what tonight's alarm will demand, and why.
///
/// This exists because an unreadable signal resolves to *away*, which
/// silently drops the two tag stages. A revoked location permission would
/// otherwise weaken the alarm with no error anywhere; here it is a sentence
/// on the home screen naming the cause.
///
/// Self-loading rather than fed from `HomeScreen`, so the screen absorbs one
/// widget and none of the state.
class HomePresenceLine extends StatefulWidget {
  /// Creates the line; [presence] is injectable so tests need no platform.
  const HomePresenceLine({super.key, this.presence});

  /// Presence resolver; defaults to the real one.
  final HomePresence? presence;

  @override
  State<HomePresenceLine> createState() => _HomePresenceLineState();
}

class _HomePresenceLineState extends State<HomePresenceLine> {
  late final HomePresence _presence = widget.presence ?? HomePresence();

  PresenceVerdict? _verdict;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    // Never throws by contract, but a platform-less test binding can still
    // fail inside SharedPreferences before resolve() gets to catch anything.
    PresenceVerdict? verdict;
    try {
      verdict = await _presence.resolve();
    } on Object {
      verdict = null;
    }
    if (!mounted) return;
    setState(() => _verdict = verdict);
  }

  @override
  Widget build(BuildContext context) {
    final verdict = _verdict;
    if (verdict == null) return const SizedBox.shrink();
    final atHome = verdict.state == PresenceState.home;
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: SpokenLabel(
        semanticLabel: atHome
            ? 'Tonight: tags required — ${verdict.detail}'
            : 'Tonight: tags skipped — ${verdict.detail}',
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              atHome ? Icons.nfc : Icons.directions_walk,
              size: 18,
              color: theme.colorScheme.onSurfaceVariant,
            ),
            const SizedBox(width: 4),
            Icon(atHome ? Icons.home : Icons.explore, size: 18),
          ],
        ),
      ),
    );
  }
}
