import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/day_calendar.dart';
import 'package:wake_alarm_sync/screens/sick_days_body.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_sync.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// The phone's picker for the shared sick-day pool (`~/src/utils/sickdays`).
///
/// Not the free-day pool, and drawn so it cannot be mistaken for it: its own
/// name, icon and fill. Every day is normal until tapped; one tap marks a
/// day sick, another clears it. Today and later only -- past days are
/// inert. No cap, no reason, no confirmation.
///
/// On a sick day every gate stands down and this phone does not ring. A
/// free day is refused here (with the pool named), so the free-day pool is
/// synced on open as well.
class SickDaysScreen extends StatefulWidget {
  /// Creates the picker; the seams are injectable for tests.
  const SickDaysScreen({
    this.openPool,
    this.syncer,
    this.openFreePool,
    this.freeSyncer,
    this.now,
    super.key,
  });

  /// Opens the sick-day pool; defaults to the on-disk one.
  final Future<SickDayPool> Function()? openPool;

  /// Syncs the sick-day pool; defaults to Firebase.
  final SickDaySync? syncer;

  /// Opens the free-day pool, for the conflict check.
  final Future<FreeDayPool> Function()? openFreePool;

  /// Syncs the free-day pool on open.
  final FreeDaySync? freeSyncer;

  /// The reference date, for tests.
  final DateTime Function()? now;

  @override
  State<SickDaysScreen> createState() => _SickDaysScreenState();
}

class _SickDaysScreenState extends State<SickDaysScreen> {
  SickDayPool? _pool;

  /// Null when it could not be opened: then no day can be marked, because
  /// "could not check" must never count as "not free".
  FreeDayPool? _free;
  bool _busy = true;
  String _status = '';
  bool _refused = false;

  late DateTime _month = DateTime(_today.year, _today.month);

  late final SickDaySync _syncer = widget.syncer ?? SickDaySync();

  DateTime get _today =>
      FreeDayPool.dateOnly(widget.now?.call() ?? DateTime.now());

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      _pool = await (widget.openPool ?? SickDayPool.open)();
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _status = 'Error: pool unavailable ($e)';
      });
      return;
    }
    await _loadFree();
    await _sync();
  }

  /// Opens and syncs the free-day pool, so a free day booked on the PC is
  /// refused here too. Its status is not shown on this screen.
  Future<void> _loadFree() async {
    try {
      final free = await (widget.openFreePool ?? FreeDayPool.open)();
      await (widget.freeSyncer ?? FreeDaySync()).sync(free);
      _free = free;
    } on Exception {
      _free = null;
    }
  }

  Future<void> _sync() async {
    final pool = _pool;
    if (pool == null) return;
    setState(() {
      _busy = true;
      _refused = false;
      _status = 'Syncing…';
    });
    final message = await _syncer.sync(pool);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _status = message;
    });
  }

  /// One tap per day: a sick day is cleared, any other is marked sick.
  Future<void> _toggle(DateTime day) async {
    final pool = _pool;
    if (pool == null) return;
    final today = _today;
    try {
      if (pool.isSick(day)) {
        await pool.remove(day, now: today);
      } else {
        final free = _free;
        if (free == null) {
          throw SickDayPolicyError(
            'Free-day pool unavailable — cannot rule out a free day on '
            '${FreeDayPool.toIso(day)}.',
          );
        }
        await pool.add(day, isFree: free.isFree, now: today);
      }
    } on SickDayPolicyError catch (e) {
      setState(() {
        _refused = true;
        _status = e.message;
      });
      return;
    }
    await _sync();
  }

  @override
  Widget build(BuildContext context) {
    final pool = _pool;
    final marks = Theme.of(context).extension<DayMarkColors>()!;
    return Scaffold(
      appBar: AppBar(
        title: const Row(
          children: [
            Icon(Icons.sick_outlined),
            SizedBox(width: 8),
            Text('Sick days'),
          ],
        ),
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
          : SickDaysBody(
              upcoming: [
                for (final day in pool.sickDays())
                  if (!day.isBefore(_today)) day,
              ],
              status: _status,
              refused: _refused,
              calendar: DayCalendar(
                month: _month,
                today: _today,
                isMarked: pool.isSick,
                busy: _busy,
                todayTappable: true,
                keyPrefix: 'sick-day',
                markColor: marks.sick,
                onMarkColor: marks.onSick,
                onTapDay: (day) => unawaited(_toggle(day)),
                onMonth: (month) => setState(() => _month = month),
                // Back to January for this year's history; forward to the
                // end of next year, the same horizon as the free days.
                firstMonth: DateTime(_today.year),
                lastMonth: DateTime(_today.year + 1, 12),
              ),
            ),
    );
  }
}
