"""Fan-out proxies — one call, applied to the same widget on every monitor.

Split out of ``_alarm_view.py`` for the 250-line cap. These are pure plumbing
over already-built widgets: nothing here constructs Tk, which is what makes
them separable from the builders that do.
"""

from __future__ import annotations

import contextlib

# Runtime import, not TYPE_CHECKING: tk.TclError is caught in a suppress()
# below, so a deferred import would raise NameError the first time a widget
# call fails — which is exactly the path these proxies exist to swallow.
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gatelock import LockConfig

    from wake_alarm._alarm_view import _AlarmView


class _LabelProxy:
    """Fans one ``configure`` call out to the same label on every monitor."""

    def __init__(self, widgets: list[tk.Label]) -> None:
        """Wrap the per-monitor copies of one label."""
        self._widgets = widgets

    def configure(self, **kwargs: str) -> None:
        """Apply the same configuration to every copy."""
        for widget in self._widgets:
            with contextlib.suppress(tk.TclError):
                widget.configure(**kwargs)


class _EntryProxy:
    """The dismiss-code entry, as seen across every monitor.

    All copies share one root-mastered ``StringVar``, so typing on whichever
    screen the user is actually looking at is the same text everywhere -- and
    reading it needs no idea of which monitor that was.
    """

    def __init__(self, widgets: list[tk.Entry], var: tk.StringVar) -> None:
        """Wrap the per-monitor entries and the variable behind them."""
        self._widgets = widgets
        self._var = var

    def get(self) -> str:
        """Return the shared text, whichever monitor it was typed on."""
        return self._var.get()

    def delete(self, _first: object, _last: object = None) -> None:
        """Clear the shared text on every monitor."""
        self._var.set("")

    def focus_force(self) -> None:
        """Focus the first entry that still exists."""
        for widget in self._widgets:
            with contextlib.suppress(tk.TclError):
                widget.focus_force()
                return


class _ViewGroup:
    """Presents N per-monitor views as if they were one.

    Every label update fans out to all monitors, and the challenge can be
    answered on any of them -- solving it anywhere dismisses the alarm
    everywhere, because every entry is the same variable and every submit
    button is the same callable.
    """

    def __init__(self, config: LockConfig, entry_var: tk.StringVar) -> None:
        """Start empty; surfaces are added as outputs come up."""
        self.config = config
        self._entry_var = entry_var
        self._views: list[_AlarmView] = []

    def add(self, view: _AlarmView) -> None:
        """Register a newly built per-monitor view."""
        self._views.append(view)

    def discard(self, output_name: str) -> None:
        """Forget the view for an output that went dark."""
        self._views = [v for v in self._views if v.output_name != output_name]

    @property
    def surfaces(self) -> list[_AlarmView]:
        """Every per-monitor view, for callers needing more than one widget."""
        return list(self._views)

    @property
    def containers(self) -> list[tk.Frame]:
        """Every per-monitor container frame."""
        return [view.container for view in self._views]

    @property
    def entry_var(self) -> tk.StringVar:
        """The one variable every monitor's entry is bound to."""
        return self._entry_var

    @property
    def entry(self) -> _EntryProxy:
        """The dismiss-code entry across all monitors."""
        return _EntryProxy([v.entry for v in self._views], self._entry_var)

    def _label(self, name: str) -> _LabelProxy:
        """Build a proxy over one named label on every monitor."""
        return _LabelProxy([getattr(view.labels, name) for view in self._views])

    @property
    def title_label(self) -> _LabelProxy:
        """The "WAKE UP!" heading on every monitor."""
        return self._label("title")

    @property
    def round_label(self) -> _LabelProxy:
        """The round counter on every monitor."""
        return self._label("round_counter")

    @property
    def info_label(self) -> _LabelProxy:
        """The challenge hint on every monitor."""
        return self._label("info")

    @property
    def code_label(self) -> _LabelProxy:
        """The challenge display on every monitor."""
        return self._label("code")

    @property
    def status_label(self) -> _LabelProxy:
        """The status line on every monitor."""
        return self._label("status")

    @property
    def timer_label(self) -> _LabelProxy:
        """The countdown on every monitor."""
        return self._label("timer")

    @property
    def escape_buttons(self) -> list[tk.Button]:
        """The escape-hatch button on every monitor."""
        return [view.escape_button for view in self._views]
