/// Validation for the morning weigh-in.
///
/// A typed number, not a Bluetooth scale — the ring path takes no plugins.
/// Two gates stand in for the hardware: the value has to be plausible, and
/// the bathroom tag has to follow it within [confirmWindow] (enforced by
/// `MorningSession`, which is what stops it being typed from bed).
library;

/// Lightest value accepted, in kg.
const double minWeightKg = 30;

/// Heaviest value accepted, in kg.
const double maxWeightKg = 250;

/// Largest overnight change accepted without retyping, in kg.
const double maxWeightJumpKg = 3;

/// How long a typed weight stays valid before the bathroom tag confirms it.
const Duration confirmWindow = Duration(minutes: 2);

/// What a weigh-in attempt came to.
enum WeightVerdict {
  /// Accepted.
  ok,

  /// Not a number.
  unparsable,

  /// Outside [minWeightKg]..[maxWeightKg].
  outOfRange,

  /// More than [maxWeightJumpKg] from the last entry; type it again to
  /// confirm.
  needsConfirm,
}

/// A checked weigh-in: the verdict, the parsed value and a line for the UI.
class WeightCheck {
  /// Creates a result.
  const WeightCheck(this.verdict, {required this.detail, this.kg});

  /// What happened.
  final WeightVerdict verdict;

  /// The parsed value, present whenever [detail] could name one.
  final double? kg;

  /// Human-readable reason, shown on the session screen.
  final String detail;

  /// Whether the value was accepted.
  bool get accepted => verdict == WeightVerdict.ok;
}

/// Parses [text] as kilograms; a decimal comma is fine.
double? parseWeight(String text) =>
    double.tryParse(text.trim().replaceAll(',', '.'));

/// Checks [text] against the range and the last known weight.
///
/// [confirming] is the value the user was just asked to retype: an identical
/// second entry passes the jump check, a different one starts over. Without
/// [last] there is nothing to jump from, so only the range applies.
WeightCheck checkWeight(String text, {double? last, double? confirming}) {
  final kg = parseWeight(text);
  if (kg == null) {
    return const WeightCheck(
      WeightVerdict.unparsable,
      detail: 'Enter your weight in kg, e.g. 72.4',
    );
  }
  if (kg < minWeightKg || kg > maxWeightKg) {
    return WeightCheck(
      WeightVerdict.outOfRange,
      kg: kg,
      detail: '$kg kg is not a body weight',
    );
  }
  if (last != null && (kg - last).abs() > maxWeightJumpKg) {
    if (confirming != kg) {
      final delta = (kg - last).toStringAsFixed(1);
      return WeightCheck(
        WeightVerdict.needsConfirm,
        kg: kg,
        detail: 'That is $delta kg from last time — type it again to confirm',
      );
    }
  }
  return WeightCheck(WeightVerdict.ok, kg: kg, detail: '$kg kg noted');
}
