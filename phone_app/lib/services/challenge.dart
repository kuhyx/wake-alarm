/// Dismiss-challenge types.
///
/// Every kind must keep its prompt **on screen until it is answered**. A
/// challenge that hides what it asked is unsolvable for someone who has just
/// walked in from another room, which is why there is no memorise-this kind.
library;

import 'dart:math';

/// Words for the reverse challenge — common, unambiguous when read half-asleep.
const List<String> _reverseWords = <String>[
  'MORNING',
  'COFFEE',
  'PILLOW',
  'BLANKET',
  'ALARM',
  'AWAKE',
  'SHOWER',
  'BREAKFAST',
  'WORKOUT',
  'WINDOW',
  'MONDAY',
  'TUESDAY',
  'FRIDAY',
  'SUNDAY',
  'WEEKEND',
];

/// The four challenge kinds. All keep their prompt visible while answering.
enum ChallengeKind {
  /// Solve an arithmetic problem.
  math,

  /// Type shuffled digits in ascending order.
  sort,

  /// Identify and continue a numeric pattern.
  sequence,

  /// Type a displayed word backwards.
  reverse,
}

/// A dismiss challenge presented to the user to prove wakefulness.
class Challenge {
  /// Creates a challenge with its display text, expected answer and hint.
  const Challenge({
    required this.kind,
    required this.display,
    required this.answer,
    required this.hint,
  });

  /// Which of the five variants this is.
  final ChallengeKind kind;

  /// Text shown in the large code label.
  final String display;

  /// Expected typed answer, normalised upper-case.
  final String answer;

  /// Short instruction shown above the code label.
  final String hint;

  /// Whether [input] solves this challenge, ignoring case and
  /// surrounding space.
  bool accepts(String input) =>
      input.trim().toUpperCase() == answer.trim().toUpperCase();
}

/// Generates challenges. The random source is injectable so tests are
/// deterministic.
class ChallengeGenerator {
  /// Creates a generator; production uses a secure random source.
  ChallengeGenerator({Random? random}) : _random = random ?? Random.secure();

  final Random _random;

  /// Picks a challenge kind at random and generates an instance.
  Challenge next() {
    final builders = <Challenge Function()>[math, sort, sequence, reverse];
    return builders[_random.nextInt(builders.length)]();
  }

  /// An arithmetic problem: addition, subtraction, multiplication or division.
  Challenge math() {
    const hint = 'Solve and type the answer';
    switch (_random.nextInt(4)) {
      case 0:
        final a = 100 + _random.nextInt(400);
        final b = 100 + _random.nextInt(400);
        return Challenge(
          kind: ChallengeKind.math,
          display: '$a + $b = ?',
          answer: '${a + b}',
          hint: hint,
        );
      case 1:
        final a = 200 + _random.nextInt(300);
        final b = 100 + _random.nextInt(a - 100);
        return Challenge(
          kind: ChallengeKind.math,
          display: '$a - $b = ?',
          answer: '${a - b}',
          hint: hint,
        );
      case 2:
        final a = 12 + _random.nextInt(14);
        final b = 3 + _random.nextInt(7);
        return Challenge(
          kind: ChallengeKind.math,
          display: '$a * $b = ?',
          answer: '${a * b}',
          hint: hint,
        );
      default:
        // Division: build a from b first so the quotient is always an integer.
        final b = 3 + _random.nextInt(8);
        final a = (10 + _random.nextInt(20)) * b;
        return Challenge(
          kind: ChallengeKind.math,
          display: '$a ÷ $b = ?',
          answer: '${a ~/ b}',
          hint: hint,
        );
    }
  }

  /// Eight shuffled digits the user must type in ascending order.
  Challenge sort() {
    final pool = List<int>.generate(9, (i) => i + 1);
    for (var i = pool.length - 1; i > 0; i--) {
      final j = _random.nextInt(i + 1);
      final tmp = pool[i];
      pool[i] = pool[j];
      pool[j] = tmp;
    }
    final digits = pool.take(8).toList();
    final ascending = List<int>.from(digits)..sort();
    return Challenge(
      kind: ChallengeKind.sort,
      display: digits.join('  '),
      answer: ascending.join(),
      hint: 'Type digits sorted lowest → highest (no spaces)',
    );
  }

  /// Four terms of an arithmetic or geometric sequence; the user gives
  /// the fifth term.
  Challenge sequence() {
    const hint = 'Find the pattern and type the next number';
    if (_random.nextInt(2) == 0) {
      final start = 2 + _random.nextInt(14);
      final step = 2 + _random.nextInt(8);
      final terms = List<int>.generate(4, (i) => start + step * i);
      return Challenge(
        kind: ChallengeKind.sequence,
        display: '${terms.join(', ')}, ?',
        answer: '${start + step * 4}',
        hint: hint,
      );
    }
    final start = 2 + _random.nextInt(5);
    final ratio = 2 + _random.nextInt(2);
    final terms = List<int>.generate(4, (i) => start * _pow(ratio, i));
    return Challenge(
      kind: ChallengeKind.sequence,
      display: '${terms.join(', ')}, ?',
      answer: '${start * _pow(ratio, 4)}',
      hint: hint,
    );
  }

  /// A common word the user must type backwards.
  Challenge reverse() {
    final word = _reverseWords[_random.nextInt(_reverseWords.length)];
    final backwards = word.split('').reversed.join();
    return Challenge(
      kind: ChallengeKind.reverse,
      display: word,
      answer: backwards,
      hint: 'Type the word backwards',
    );
  }

  /// Integer exponentiation; `pow` returns a `num` and would need a cast.
  static int _pow(int base, int exponent) {
    var result = 1;
    for (var i = 0; i < exponent; i++) {
      result *= base;
    }
    return result;
  }
}
