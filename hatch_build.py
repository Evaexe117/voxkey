"""Build hook: compile the gettext catalogues into the wheel.

The .po sources are tracked in git; the compiled .mo files are build output and
are git-ignored. Without this hook the wheel would ship only the .po sources and
the runtime would silently fall back to English, so the French UI would not work
for anyone who installed voxkey. The hook runs the same pure-Python compiler the
developer uses (tools/compile_catalogs.py), and the wheel target force-includes
the generated .mo via the `artifacts` setting in pyproject.toml.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CompileCatalogsHook(BuildHookInterface):
    def initialize(
        self,
        version: str,  # noqa: ARG002
        build_data: dict[str, Any],  # noqa: ARG002
    ) -> None:
        root = Path(self.root)
        sys.path.insert(0, str(root / "tools"))
        import compile_catalogs

        compile_catalogs.main()
