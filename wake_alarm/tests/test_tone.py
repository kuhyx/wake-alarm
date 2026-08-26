"""Tests for alarm tone synthesis and caching."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    import pathlib

from wake_alarm._tone import _ensure_tone_wav


class TestEnsureToneWav:
    """Tests for _ensure_tone_wav (sine WAV generator + cache)."""

    def test_generates_and_caches(self, tmp_path: pathlib.Path) -> None:
        """First call generates the WAV; second call returns the cached path."""
        from wake_alarm import _tone as tone_mod

        tone_mod._TONE_CACHE.clear()
        with patch(
            "wake_alarm._tone.tempfile.gettempdir",
            return_value=str(tmp_path),
        ):
            path1 = _ensure_tone_wav(440)
            assert path1.exists()
            size = path1.stat().st_size
            assert size > 0
            # Second call must hit the cache (no regeneration).
            with patch("wake_alarm._tone.wave.open") as mock_open:
                path2 = _ensure_tone_wav(440)
                mock_open.assert_not_called()
            assert path2 == path1
        tone_mod._TONE_CACHE.clear()

    def test_regenerates_when_cached_file_missing(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """If the cached file was deleted, regenerate it."""
        from wake_alarm._tone import _TONE_CACHE

        _TONE_CACHE.clear()
        with patch(
            "wake_alarm._tone.tempfile.gettempdir",
            return_value=str(tmp_path),
        ):
            path1 = _ensure_tone_wav(880)
            path1.unlink()
            path2 = _ensure_tone_wav(880)
            assert path2.exists()
        _TONE_CACHE.clear()
