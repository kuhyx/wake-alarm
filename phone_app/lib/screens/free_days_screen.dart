import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/screens/day_calendar.dart';
import 'package:wake_alarm_sync/screens/free_days_body.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_sync.dart';
import 'package:wake_alarm_sync/ui/cues.dart';

/// The one picker for the shared free-day pool.
///
/// A day marked here stands down every gate app at once — the PC lockers,
/// diet guard, leetcode guard, home guard, and this alarm — and none of them
/// mentions it afterwards. There is no notification, no low-budget warning
/// and no prompt at ring time; you find out how many are left by opening
/// this screen.
///
/// Syncs on open and after every change. A day marked on the PC reaches the
/// phone when this app launches, when this screen opens, or at the next
/// pre-alarm sync (`DOCS-sick-days.md`). Marking on the phone is immediate.
///
/// A sick day is never also a free day: the sick-day pool is synced on open
/// too, and a sick date is refused here with the pool named.
class FreeDaysScreen extends StatefulWidget {
  /// Creates the picker; the seams are injectable for tests.
  const FreeDaysScreen({
    this.openPool,
    this.syncer,
    this.openSickPool,
    this.sickSyncer,
    this.now,
    super.key,
  });

  /// Opens the pool; defaults to the on-disk one.
  final Future<FreeDayPool> Function()? openPool;

  /// Syncs the pool; defaults to Firebase.
  final FreeDaySync? syncer;

  /// Opens the sick-day pool, for the conflict check.
  final Future<SickDayPool> Function()? openSickPool;

  /// Syncs the sick-day pool on open.
  final SickDaySync? sickSyncer;

  /// The reference date, for tests.
  final DateTime Function()? now;

  @override
  State<FreeDaysScreen> createState() => _FreeDaysScreenState();
}

class _FreeDaysScreenState extends State<FreeDaysScreen> {
  FreeDayPool? _pool;

  /// Null when it could not be opened: then no day can be booked, because
  /// "could not check" must never count as "not sick".
  SickDayPool? _sick;
  bool _busy = true;
  String _status = '';

  /// The month the calendar shows; starts on the current one.
  late DateTime _month = DateTime(_today.year, _today.month);

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
    await _loadSick();
    await _sync();
  }

  /// Opens and syncs the sick-day pool, so a sick day marked on the PC is
  /// refused here too. Its sync status is not shown: this is the free-day
  /// screen, and the cache it refreshes is the sick-day one.
  Future<void> _loadSick() async {
    try {
      final sick = await (widget.openSickPool ?? SickDayPool.open)();
      await (widget.sickSyncer ?? SickDaySync()).sync(sick);
      _sick = sick;
    } on Exception {
      _sick = null;
    }
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

  /// One tap per day: a free day is given back, any other is taken.
  ///
  /// No reason prompt and no confirmation -- a future release refunds the
  /// budget, so a mis-tap costs one more tap. The calendar only reports
  /// future dates, so today and the past never reach here.
  Future<void> _toggle(DateTime day) async {
    final pool = _pool;
    if (pool == null) return;
    final today = _today;
    await _apply(
      () => pool.isFree(day)
          ? pool.release(day, now: today)
          : _mark(pool, day, today),
    );
  }

  /// Books [day] unless the sick-day pool holds it (or cannot be read).
  Future<void> _mark(FreeDayPool pool, DateTime day, DateTime today) async {
    final iso = FreeDayPool.toIso(day);
    final sick = _sick;
    if (sick == null) {
      throw FreeDayPolicyError(
        'Sick-day pool unavailable — cannot rule out a sick day on $iso.',
      );
    }
    if (sick.isSick(day)) {
      throw FreeDayPolicyError(
        '$iso is a sick day — clear it in Sick days first.',
      );
    }
    await pool.mark(day, now: today);
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
        // title removed
        actions: [
          IconButton(
            icon: const Icon(Icons.sync, semanticLabel: 'Sync now'),
            onPressed: _busy ? null : () => unawaited(_sync()),
          ),
        ],
      ),
      body: pool == null
          ? Center(
              child: _status.isEmpty
                  ? const CircularProgressIndicator()
                  : StatusCue(semanticLabel: _status),
            )
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
              calendar: DayCalendar(
                month: _month,
                today: _today,
                isMarked: pool.isFree,
                busy: _busy,
                onTapDay: (day) => unawaited(_toggle(day)),
                onMonth: (month) => setState(() => _month = month),
                // Back to January shows this year's spent days; forward to
                // the end of next year, the pool's booking horizon.
                firstMonth: DateTime(_today.year),
                lastMonth: DateTime(_today.year + 1, 12),
              ),
            ),
    );
  }
}
