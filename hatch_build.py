"""Build hook: compile the gettext catalogues into the wheel.

The .po sources are tracked in git; the compiled .mo files are build output and
are git-ignored. Without this hook the wheel would ship only the .po sources and
the runtime would silently fall back to English, so the French UI would not work
for anyone who installed voxkey. The hook compiles the catalogues into a build
temp directory and force-includes them, so it never writes into the source tree
and a read-only source tree still builds.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CompileCatalogsHook(BuildHookInterface):
    def initialize(
        self,
        version: str,  # noqa: ARG002
        build_data: dict[str, Any],
    ) -> None:
        sys.path.insert(0, str(Path(self.root) / "tools"))
        import compile_catalogs

        dest = Path(tempfile.mkdtemp(prefix="voxkey-mo-"))
        mapping = compile_catalogs.compile_into(dest)
        build_data.setdefault("force_include", {}).update(mapping)
