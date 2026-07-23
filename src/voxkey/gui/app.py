"""The control window: a GTK notebook of Status and Settings.

A thin shell. It drives the daemon through ``service`` and edits the same TOML
file every other client reads, through ``model``. GTK is imported here, never at
package import, so a headless ``voxkey serve`` never needs it.
"""

from __future__ import annotations

import gi

try:
    gi.require_version("Gtk", "3.0")
except ValueError as error:  # namespace missing: report it as an import failure
    raise ImportError(str(error)) from error

from gi.repository import Gtk  # noqa: E402

from voxkey.gui.page_settings import SettingsPage  # noqa: E402
from voxkey.gui.page_status import StatusPage  # noqa: E402
from voxkey.i18n import _, setup  # noqa: E402


def build_window() -> Gtk.Window:
    window = Gtk.Window(title=_("voxkey"))
    window.set_default_size(480, 440)
    window.set_border_width(12)

    notebook = Gtk.Notebook()
    notebook.append_page(StatusPage().widget, Gtk.Label(label=_("Status")))
    notebook.append_page(SettingsPage().widget, Gtk.Label(label=_("Settings")))
    window.add(notebook)

    window.connect("destroy", Gtk.main_quit)
    return window


def run() -> int:
    """Open the control window until it is closed."""
    setup()
    build_window().show_all()
    Gtk.main()
    return 0
