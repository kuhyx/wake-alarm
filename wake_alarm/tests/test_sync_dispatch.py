"""Tests for fetch_remote_alarm's backend ordering.

Split from test_sync_backends.py for the 250-line cap.
"""

from __future__ import annotations

from unittest.mock import patch

from wake_alarm._sync import fetch_remote_alarm


class TestFetchRemoteAlarmDispatch:
    """Tests for the Firebase-first, GitHub-fallback ordering."""

    def test_prefers_firebase(self) -> None:
        """When Firebase answers, GitHub is never asked."""
        with (
            patch(
                "wake_alarm._sync_transport._fetch_firebase_alarm", return_value=(6, 15)
            ),
            patch("wake_alarm._sync_transport._fetch_github_alarm") as github,
        ):
            resolved = fetch_remote_alarm()
            assert resolved is not None
            assert resolved[:2] == (6, 15)
        github.assert_not_called()

    def test_falls_back_to_github(self) -> None:
        """A Firebase miss still resolves through the mirror."""
        with (
            patch(
                "wake_alarm._sync_transport._fetch_firebase_alarm", return_value=None
            ),
            patch(
                "wake_alarm._sync_transport._fetch_github_alarm",
                return_value=(7, 30, None),
            ),
        ):
            resolved = fetch_remote_alarm()
            assert resolved is not None
            assert resolved[:2] == (7, 30)

    def test_both_missing_yields_none(self) -> None:
        """With neither backend usable the caller degrades to the cache."""
        with (
            patch(
                "wake_alarm._sync_transport._fetch_firebase_alarm", return_value=None
            ),
            patch("wake_alarm._sync_transport._fetch_github_alarm", return_value=None),
        ):
            assert fetch_remote_alarm() is None
