"""Compile .po catalogues into .mo files without depending on gettext tools.

The MO format is a small, stable, documented binary layout, so implementing it
here removes a build dependency that would otherwise have to be present on
every machine that builds a wheel.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

MAGIC = 0x950412DE

# The escapes gettext defines inside a quoted PO string.
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def _unquote(text: str) -> str:
    """Resolve PO escape sequences without touching anything else.

    The obvious shortcut, ``text.encode().decode("unicode_escape")``, silently
    mangles every non-ASCII character: it encodes as UTF-8 and decodes as
    Latin-1, so "détectée" comes back as mojibake. Accented translations are
    the entire point of shipping a French catalogue, so the escapes are
    resolved by hand instead.
    """
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            index += 1
            out.append(_ESCAPES.get(text[index], text[index]))
        else:
            out.append(char)
        index += 1
    return "".join(out)


def parse_po(po_text: str) -> dict[str, str]:
    """Extract msgid/msgstr pairs. Fuzzy and empty translations are dropped."""
    entries: dict[str, str] = {}
    msgid: list[str] = []
    msgstr: list[str] = []
    current: str | None = None
    fuzzy = False
    pending_fuzzy = False

    def flush() -> None:
        nonlocal msgid, msgstr, current, fuzzy
        if current is not None:
            key = "".join(msgid)
            value = "".join(msgstr)
            if value and not fuzzy:
                entries[key] = value
        msgid, msgstr, current, fuzzy = [], [], None, False

    for raw_line in po_text.splitlines():
        line = raw_line.strip()
        if line.startswith("#,") and "fuzzy" in line:
            pending_fuzzy = True
            continue
        if line.startswith("#") or not line:
            continue
        if line.startswith("msgid "):
            flush()
            fuzzy = pending_fuzzy
            pending_fuzzy = False
            current = "msgid"
            msgid.append(_unquote(line[len("msgid ") :].strip('"')))
        elif line.startswith("msgstr "):
            current = "msgstr"
            msgstr.append(_unquote(line[len("msgstr ") :].strip('"')))
        elif line.startswith('"') and current == "msgid":
            msgid.append(_unquote(line.strip('"')))
        elif line.startswith('"') and current == "msgstr":
            msgstr.append(_unquote(line.strip('"')))
    flush()
    return entries


def compile_po(po_text: str) -> bytes:
    """Render the catalogue as a little-endian MO file."""
    entries = parse_po(po_text)
    keys = sorted(entries)
    ids = b"\x00".join(key.encode() for key in keys) + (b"\x00" if keys else b"")
    strings = b"\x00".join(entries[key].encode() for key in keys) + (
        b"\x00" if keys else b""
    )

    count = len(keys)
    key_table_offset = 28
    value_table_offset = key_table_offset + count * 8
    ids_offset = value_table_offset + count * 8
    strings_offset = ids_offset + len(ids)

    key_table = b""
    value_table = b""
    id_cursor = ids_offset
    string_cursor = strings_offset
    for key in keys:
        encoded_key = key.encode()
        encoded_value = entries[key].encode()
        key_table += struct.pack("<II", len(encoded_key), id_cursor)
        value_table += struct.pack("<II", len(encoded_value), string_cursor)
        id_cursor += len(encoded_key) + 1
        string_cursor += len(encoded_value) + 1

    header = struct.pack(
        "<IiIIIii", MAGIC, 0, count, key_table_offset, value_table_offset, 0, 0
    )
    return header + key_table + value_table + ids + strings


def locales_root() -> Path:
    return Path(__file__).resolve().parents[1] / "src" / "voxkey" / "locales"


def compile_into(dest_dir: Path) -> dict[str, str]:
    """Compile every catalogue into ``dest_dir``, mirroring the package layout.

    Returns a mapping from each written .mo (absolute path) to its path relative
    to the package root ("voxkey/locales/.../voxkey.mo"). The build hook uses
    this to force-include the generated files without writing into the source
    tree, so a read-only source tree still builds.
    """
    root = locales_root()
    mapping: dict[str, str] = {}
    for po_path in root.rglob("*.po"):
        relative = po_path.relative_to(root.parent.parent).with_suffix(".mo")
        mo_path = dest_dir / relative
        mo_path.parent.mkdir(parents=True, exist_ok=True)
        mo_path.write_bytes(compile_po(po_path.read_text()))
        mapping[str(mo_path)] = str(relative)
    return mapping


def main() -> int:
    """Compile catalogues in place, for the developer workflow."""
    compiled = 0
    for po_path in locales_root().rglob("*.po"):
        mo_path = po_path.with_suffix(".mo")
        mo_path.write_bytes(compile_po(po_path.read_text()))
        print(f"compiled {po_path} -> {mo_path}")
        compiled += 1
    if compiled == 0:
        print("no catalogues found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
