"""The control window and its pure logic.

``model`` holds every decision the window makes and imports no GTK, so it is
tested directly. ``app`` and the ``page_*`` modules are thin GTK shells that
import PyGObject lazily; importing this package must not require GTK.
"""

from __future__ import annotations
