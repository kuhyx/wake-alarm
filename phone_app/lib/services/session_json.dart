import 'package:wake_alarm_sync/services/morning_session.dart';

/// JSON for [MorningSession]: SharedPreferences and the synced record share
/// one shape, so a session restored from a peer reads like a local one.
extension SessionJson on MorningSession {
  /// Serialises for SharedPreferences and the synced record.
  Map<String, Object?> toJson() => <String, Object?>{
    'date': date,
    'started_at': startedAt.toIso8601String(),
    'updated_at': updatedAt.toIso8601String(),
    'bathroom_tag_required': bathroomTagRequired,
    'passed': <String, Object?>{
      for (final e in passedAt.entries)
        e.key.name: <String, Object?>{
          'at': e.value.toIso8601String(),
          'how': passedHow[e.key]?.name,
        },
    },
    'deadline_rung': deadlineRung.map((l) => l.name).toList(),
    'weight_kg': weightKg,
    'energy': energy,
    'pending_weight_kg': pendingWeightKg,
    'pending_weight_at': pendingWeightAt?.toIso8601String(),
    're_rings': reRings,
    're_ring_reasons': reRingReasons,
    'pending_re_ring_reason': pendingReRingReason,
    'outcome': outcome.name,
  };
}

/// Restores from [SessionJson.toJson]; null when the shape is not a session.
MorningSession? sessionFromJson(Object? raw) {
  if (raw is! Map) return null;
  final date = raw['date'];
  final started = DateTime.tryParse('${raw['started_at']}');
  if (date is! String || started == null) return null;
  final passed = raw['passed'];
  final passedAt = <SessionLeg, DateTime>{};
  final passedHow = <SessionLeg, LegPass>{};
  if (passed is Map) {
    for (final leg in SessionLeg.values) {
      final entry = passed[leg.name];
      if (entry is! Map) continue;
      final at = DateTime.tryParse('${entry['at']}');
      if (at == null) continue;
      passedAt[leg] = at;
      passedHow[leg] = LegPass.values.asNameMap()[entry['how']] ?? LegPass.tag;
    }
  }
  final rung = raw['deadline_rung'];
  final reasons = raw['re_ring_reasons'];
  return MorningSession(
    date: date,
    startedAt: started,
    updatedAt: DateTime.tryParse('${raw['updated_at']}') ?? started,
    bathroomTagRequired: raw['bathroom_tag_required'] != false,
    passedAt: passedAt,
    passedHow: passedHow,
    deadlineRung: <SessionLeg>{
      if (rung is List)
        for (final name in rung) ?SessionLeg.values.asNameMap()[name],
    },
    weightKg: (raw['weight_kg'] as num?)?.toDouble(),
    energy: (raw['energy'] as num?)?.toInt(),
    pendingWeightKg: (raw['pending_weight_kg'] as num?)?.toDouble(),
    pendingWeightAt: DateTime.tryParse('${raw['pending_weight_at']}'),
    reRings: (raw['re_rings'] as num?)?.toInt() ?? 0,
    reRingReasons: reasons is List
        ? reasons.whereType<String>().toList()
        : <String>[],
    pendingReRingReason: raw['pending_re_ring_reason'] as String?,
    outcome:
        SessionOutcome.values.asNameMap()[raw['outcome']] ??
        SessionOutcome.active,
  );
}
