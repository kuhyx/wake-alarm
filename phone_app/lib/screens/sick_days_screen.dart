import 'dart:async';

import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/screens/day_calendar.dart';
import 'package:wake_alarm_sync/screens/sick_day_sheet.dart';
import 'package:wake_alarm_sync/screens/sick_days_body.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_sync.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// The phone's picker for the shared sick-day pool (`~/src/utils/sickdays`).
///
/// Not the free-day pool, and drawn so it cannot be mistaken for it: its own
/// name, icon and fill. Every day is normal until marked. Tapping today or
/// a later day opens [SickDaySheet]: one switch per locker, all off, and
/// "Mark sick"; on a sick day, its current switches, "Save" (a keep-only
/// edit) and "Clear sick day". Past days are inert. No cap, no reason.
///
/// On a sick day every locker left off stands down; a kept one behaves as
/// on a normal day (the cell carries a dot). This phone does not ring only
/// when the alarm is not kept. A free day is refused before the sheet opens
/// (with the pool named), so the free-day pool is synced on open as well.
class SickDaysScreen extends StatefulWidget {
  /// Creates the picker; the seams are injectable for tests.
  const SickDaysScreen({
    this.openPool,
    this.syncer,
    this.openFreePool,
    this.freeSyncer,
    this.now,
    this.scheduler,
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

  /// Reads the native cache back; defaults to the real channel.
  final AlarmScheduler? scheduler;

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

  /// What the native ring-path cache holds, read back over the channel.
  List<String>? _cache;
  bool _cacheRead = false;

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
    // Read before syncing too: the sync rewrites the cache, so only this
    // read shows what earlier marks left there.
    await _readCache();
    await _loadFree();
    await _sync();
  }

  /// Shows the native cache `AlarmReceiver` reads, not the Dart pool.
  /// Unreadable is never shown as "none": the ring treats it as no sick day.
  Future<void> _readCache() async {
    List<String>? dates;
    try {
      dates = await (widget.scheduler ?? AlarmScheduler()).getSickDays();
    } on Object {
      dates = null;
    }
    if (!mounted) return;
    setState(() {
      _cache = dates;
      _cacheRead = true;
    });
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
    await _readCache();
    if (!mounted) return;
    setState(() {
      _busy = false;
      _status = message;
    });
  }

  /// Opens the per-locker sheet for [day] and applies what it returns.
  Future<void> _onTapDay(DateTime day) async {
    final pool = _pool;
    if (pool == null) return;
    final sick = pool.isSick(day);
    final refusal = sick ? null : freeDayRefusal(_free, day);
    if (refusal != null) {
      setState(() {
        _refused = true;
        _status = refusal;
      });
      return;
    }
    final result = await showSickDaySheet(
      context,
      day: day,
      isSick: sick,
      kept: pool.keptLockers(day),
    );
    if (result == null || !mounted) return;
    final bool wrote;
    try {
      wrote = await applySickSheet(pool, day, result, free: _free, now: _today);
    } on SickDayPolicyError catch (e) {
      setState(() {
        _refused = true;
        _status = e.message;
      });
      return;
    }
    if (wrote) await _sync();
  }

  @override
  Widget build(BuildContext context) {
    final pool = _pool;
    final marks = Theme.of(context).extension<DayMarkColors>()!;
    return Scaffold(
      appBar: AppBar(
        title: const Row(children: [Icon(Icons.sick_outlined)]),
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
          : SickDaysBody(
              upcoming: [
                for (final day in pool.sickDays())
                  if (!day.isBefore(_today)) day,
              ],
              keptOf: pool.keptLockers,
              status: _status,
              cache: _cache,
              cacheRead: _cacheRead,
              refused: _refused,
              calendar: DayCalendar(
                month: _month,
                today: _today,
                isMarked: pool.isSick,
                hasBadge: (day) => pool.keptLockers(day).isNotEmpty,
                busy: _busy,
                todayTappable: true,
                keyPrefix: 'sick-day',
                markColor: marks.sick,
                onMarkColor: marks.onSick,
                onTapDay: (day) => unawaited(_onTapDay(day)),
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
