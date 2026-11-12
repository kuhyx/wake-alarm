import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/challenge.dart';

/// Deterministic source so every branch can be reached on purpose.
class _FixedRandom implements Random {
  _FixedRandom(this._values);

  final List<int> _values;
  int _at = 0;

  @override
  int nextInt(int max) {
    final v = _values[_at % _values.length];
    _at++;
    return v % max;
  }

  @override
  bool nextBool() => nextInt(2) == 0;

  @override
  double nextDouble() => 0;
}

void main() {
  group('Challenge.accepts', () {
    const challenge = Challenge(
      kind: ChallengeKind.math,
      display: '1 + 1 = ?',
      answer: '2',
      hint: 'h',
    );

    test('accepts the exact answer', () {
      expect(challenge.accepts('2'), isTrue);
    });

    test('ignores case and surrounding whitespace', () {
      const word = Challenge(
        kind: ChallengeKind.reverse,
        display: 'd',
        answer: 'MRALA',
        hint: 'h',
      );
      expect(word.accepts('  mrala '), isTrue);
    });

    test('rejects a wrong answer', () {
      expect(challenge.accepts('3'), isFalse);
    });
  });

  group('ChallengeGenerator', () {
    test('math covers addition', () {
      final c = ChallengeGenerator(random: _FixedRandom(<int>[0, 5, 7])).math();
      expect(c.kind, ChallengeKind.math);
      expect(c.display, contains('+'));
      final parts = RegExp(r'(\d+) \+ (\d+)').firstMatch(c.display)!;
      final sum = int.parse(parts.group(1)!) + int.parse(parts.group(2)!);
      expect(c.answer, '$sum');
    });

    test('math covers subtraction with a non-negative result', () {
      final c = ChallengeGenerator(random: _FixedRandom(<int>[1, 5, 7])).math();
      expect(c.display, contains('-'));
      expect(int.parse(c.answer), greaterThanOrEqualTo(0));
    });

    test('math covers multiplication', () {
      final c = ChallengeGenerator(random: _FixedRandom(<int>[2, 3, 4])).math();
      expect(c.display, contains('*'));
      final parts = RegExp(r'(\d+) \* (\d+)').firstMatch(c.display)!;
      final product = int.parse(parts.group(1)!) * int.parse(parts.group(2)!);
      expect(c.answer, '$product');
    });

    test('math division always has an integer answer', () {
      final c = ChallengeGenerator(random: _FixedRandom(<int>[3, 2, 6])).math();
      expect(c.display, contains('÷'));
      final parts = RegExp(r'(\d+) ÷ (\d+)').firstMatch(c.display)!;
      final a = int.parse(parts.group(1)!);
      final b = int.parse(parts.group(2)!);
      expect(a % b, 0);
      expect(c.answer, '${a ~/ b}');
    });

    test('sort shows eight digits and answers them ascending', () {
      final c = ChallengeGenerator().sort();
      final shown = c.display.split('  ').map(int.parse).toList();
      expect(shown, hasLength(8));
      expect(c.answer, (List<int>.from(shown)..sort()).join());
      expect(c.answer.split('').toSet(), hasLength(8));
    });

    test('sequence covers the arithmetic branch', () {
      final c = ChallengeGenerator(
        random: _FixedRandom(<int>[0, 3, 2]),
      ).sequence();
      final terms = c.display
          .replaceAll(', ?', '')
          .split(', ')
          .map(int.parse)
          .toList();
      final step = terms[1] - terms[0];
      expect(terms[3] - terms[2], step);
      expect(c.answer, '${terms[3] + step}');
    });

    test('sequence covers the geometric branch', () {
      final c = ChallengeGenerator(
        random: _FixedRandom(<int>[1, 2, 0]),
      ).sequence();
      final terms = c.display
          .replaceAll(', ?', '')
          .split(', ')
          .map(int.parse)
          .toList();
      final ratio = terms[1] ~/ terms[0];
      expect(terms[3], terms[2] * ratio);
      expect(c.answer, '${terms[3] * ratio}');
    });

    test('reverse expects the word backwards', () {
      final c = ChallengeGenerator().reverse();
      final word = c.display.split('\n').last;
      expect(c.answer, word.split('').reversed.join());
    });

    test('every kind keeps its prompt on screen while it is answered', () {
      // The memorise-then-hide kind was deleted outright rather than merely
      // left out of the rotation, so this is now an enum-level guarantee: a
      // challenge that hides itself is unsolvable for someone who has just
      // walked in from another room.
      for (var i = 0; i < 400; i++) {
        final c = ChallengeGenerator().next();
        expect(c.display, isNotEmpty, reason: '${c.kind} showed nothing');
      }
      expect(ChallengeKind.values, hasLength(4));
    });

    test('next() produces every kind that is safe to show', () {
      final kinds = <ChallengeKind>{};
      for (var i = 0; i < 400; i++) {
        kinds.add(ChallengeGenerator().next().kind);
      }
      expect(kinds, <ChallengeKind>{
        ChallengeKind.math,
        ChallengeKind.sort,
        ChallengeKind.sequence,
        ChallengeKind.reverse,
      });
    });
  });
}
