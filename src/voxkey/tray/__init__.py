"""The system-tray status icon.

``icons`` maps the runtime state to an asset and a tooltip and imports no GTK,
so it is tested directly. ``app`` is the thin AyatanaAppIndicator shell,
imported lazily by the ``voxkey tray`` command; importing this package must not
require GTK.
"""

from __future__ import annotations
