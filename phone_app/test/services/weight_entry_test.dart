import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/weight_entry.dart';

void main() {
  test('parses a decimal comma', () {
    expect(parseWeight(' 72,4 '), 72.4);
    expect(parseWeight('abc'), isNull);
  });

  test('accepts a plausible first weigh-in', () {
    final check = checkWeight('72.4');
    expect(check.accepted, isTrue);
    expect(check.kg, 72.4);
    expect(check.detail, contains('72.4'));
  });

  test('rejects nonsense and out-of-range values', () {
    expect(checkWeight('').verdict, WeightVerdict.unparsable);
    expect(checkWeight('12').verdict, WeightVerdict.outOfRange);
    expect(checkWeight('300').verdict, WeightVerdict.outOfRange);
    expect(checkWeight('12').accepted, isFalse);
  });

  test('a jump from last time must be retyped', () {
    final first = checkWeight('76', last: 72);
    expect(first.verdict, WeightVerdict.needsConfirm);
    expect(first.detail, contains('4.0 kg'));
    expect(checkWeight('76', last: 72, confirming: 76).accepted, isTrue);
    expect(checkWeight('77', last: 72, confirming: 76).accepted, isFalse);
    expect(checkWeight('74', last: 72).accepted, isTrue);
  });
}
