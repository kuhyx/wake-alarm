import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/free_days_body.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';

/// The one picker for the shared free-day pool.
///
/// A day marked here stands down every gate app at once — the PC lockers,
/// diet guard, leetcode guard, home guard, and this alarm — and none of them
/// mentions it afterwards. There is no notification, no low-budget warning
/// and no prompt at ring time; you find out how many are left by opening
/// this screen.
///
/// Syncs on open and after every change. A day marked on the PC reaches the
/// phone the next time this app launches or this screen opens — the ring
/// path takes no background dependency, so an overnight PC mark can miss
/// the morning ring. Marking on the phone is immediate.
class FreeDaysScreen extends StatefulWidget {
  /// Creates the picker; the seams are injectable for tests.
  const FreeDaysScreen({this.openPool, this.syncer, this.now, super.key});

  /// Opens the pool; defaults to the on-disk one.
  final Future<FreeDayPool> Function()? openPool;

  /// Syncs the pool; defaults to Firebase.
  final FreeDaySync? syncer;

  /// The reference date, for tests.
  final DateTime Function()? now;

  @override
  State<FreeDaysScreen> createState() => _FreeDaysScreenState();
}

class _FreeDaysScreenState extends State<FreeDaysScreen> {
  FreeDayPool? _pool;
  bool _busy = true;
  String _status = '';

  late final FreeDaySync _syncer = widget.syncer ?? FreeDaySync();

  DateTime get _today =>
      FreeDayPool.dateOnly(widget.now?.call() ?? DateTime.now());

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      _pool = await (widget.openPool ?? FreeDayPool.open)();
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _status = 'Error: pool unavailable ($e)';
      });
      return;
    }
    await _sync();
  }

  Future<void> _sync() async {
    final pool = _pool;
    if (pool == null) return;
    setState(() {
      _busy = true;
      _status = 'Syncing…';
    });
    final message = await _syncer.sync(pool);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _status = message;
    });
  }

  Future<void> _pickDay() async {
    final pool = _pool;
    if (pool == null) return;
    final today = _today;
    final picked = await showDatePicker(
      context: context,
      initialDate: today,
      firstDate: today,
      lastDate: DateTime(today.year + 1, 12, 31),
      helpText: 'Take a free day',
      selectableDayPredicate: (day) => !pool.isFree(day),
    );
    if (picked == null || !mounted) return;
    final reason = await _askReason();
    if (!mounted) return;
    await _apply(() => pool.mark(picked, reason: reason ?? '', now: today));
  }

  /// Optional, by design. Enter with an empty field and nothing is stored.
  Future<String?> _askReason() {
    final controller = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Reason (optional)'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(hintText: 'e.g. travelling'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(controller.text),
            child: const Text('Mark free'),
          ),
        ],
      ),
    );
  }

  Future<void> _release(DateTime day) async {
    final pool = _pool;
    if (pool == null) return;
    await _apply(() => pool.release(day, now: _today));
  }

  /// Runs a pool edit, reports a refusal in the status line, and syncs.
  Future<void> _apply(Future<void> Function() edit) async {
    try {
      await edit();
    } on FreeDayPolicyError catch (e) {
      setState(() => _status = e.message);
      return;
    }
    await _sync();
  }

  @override
  Widget build(BuildContext context) {
    final pool = _pool;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Free days'),
        actions: [
          IconButton(
            icon: const Icon(Icons.sync),
            tooltip: 'Sync now',
            onPressed: _busy ? null : () => unawaited(_sync()),
          ),
        ],
      ),
      body: pool == null
          ? Center(child: Text(_status.isEmpty ? 'Loading…' : _status))
          : FreeDaysBody(
              year: _today.year,
              remaining: pool.remaining(_today.year),
              upcoming: [
                for (final day in pool.freeDays())
                  if (!day.isBefore(_today))
                    (day: day, reason: pool.reasonFor(day)),
              ],
              status: _status,
              busy: _busy,
              onRelease: (day) => unawaited(_release(day)),
            ),
      floatingActionButton: pool == null
          ? null
          : FloatingActionButton.extended(
              onPressed: _busy ? null : () => unawaited(_pickDay()),
              icon: const Icon(Icons.event_available),
              label: const Text('Take a day'),
            ),
    );
  }
}
