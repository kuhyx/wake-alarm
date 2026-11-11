import 'dart:math' show pi;

import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/ui/spoken_label.dart';

/// A dashed outline slot for an empty/unregistered value.
/// Paints no text; spoken label is provided via [SpokenLabel].
class DashedSlot extends StatelessWidget {
  /// Creates a dashed slot.
  const DashedSlot({super.key});

  @override
  Widget build(BuildContext context) {
    final outlineColor = Theme.of(context).colorScheme.outline;
    return SpokenLabel(
      semanticLabel: 'none registered',
      child: CustomPaint(
        painter: _DashedSlotPainter(outlineColor: outlineColor),
        child: const SizedBox(height: 40),
      ),
    );
  }
}

class _DashedSlotPainter extends CustomPainter {
  const _DashedSlotPainter({required this.outlineColor});

  final Color outlineColor;
  static const _dashWidth = 6.0;
  static const _dashGap = 4.0;
  static const _radius = 8.0;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = outlineColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;

    // Top edge
    _drawDashedLine(
      canvas,
      paint,
      const Offset(_radius, 0),
      Offset(size.width - _radius, 0),
    );
    // Top-right arc
    _drawDashedArc(
      canvas,
      paint,
      Offset(size.width - _radius, _radius),
      _radius,
      -pi / 2,
      pi / 2,
    );
    // Right edge
    _drawDashedLine(
      canvas,
      paint,
      Offset(size.width, _radius),
      Offset(size.width, size.height - _radius),
    );
    // Bottom-right arc
    _drawDashedArc(
      canvas,
      paint,
      Offset(size.width - _radius, size.height - _radius),
      _radius,
      0,
      pi / 2,
    );
    // Bottom edge
    _drawDashedLine(
      canvas,
      paint,
      Offset(size.width - _radius, size.height),
      Offset(_radius, size.height),
    );
    // Bottom-left arc
    _drawDashedArc(
      canvas,
      paint,
      Offset(_radius, size.height - _radius),
      _radius,
      pi / 2,
      pi / 2,
    );
    // Left edge
    _drawDashedLine(
      canvas,
      paint,
      Offset(0, size.height - _radius),
      const Offset(0, _radius),
    );
    // Top-left arc
    _drawDashedArc(
      canvas,
      paint,
      const Offset(_radius, _radius),
      _radius,
      pi,
      pi / 2,
    );
  }

  void _drawDashedLine(Canvas canvas, Paint paint, Offset start, Offset end) {
    final delta = end - start;
    final length = delta.distance;
    if (length <= 0) return;
    final unit = delta / length;
    var pos = 0.0;
    while (pos < length) {
      final dashEnd = (pos + _dashWidth < length) ? pos + _dashWidth : length;
      canvas.drawLine(start + unit * pos, start + unit * dashEnd, paint);
      pos += _dashWidth + _dashGap;
    }
  }

  void _drawDashedArc(
    Canvas canvas,
    Paint paint,
    Offset center,
    double radius,
    double startAngle,
    double sweepAngle,
  ) {
    final arcLength = radius * sweepAngle.abs();
    var pos = 0.0;
    while (pos < arcLength) {
      final dashEnd = (pos + _dashWidth < arcLength)
          ? pos + _dashWidth
          : arcLength;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        startAngle + (sweepAngle > 0 ? pos : -pos) / radius,
        (dashEnd - pos) / radius * (sweepAngle > 0 ? 1 : -1),
        false,
        paint,
      );
      pos += _dashWidth + _dashGap;
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
