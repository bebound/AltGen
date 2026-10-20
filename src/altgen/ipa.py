"""Read app metadata from an IPA without extracting it.

An IPA is a zip archive with the app bundle at ``Payload/<name>.app``; the
app's version lives in that bundle's ``Info.plist``. Some projects publish
releases whose GitHub tag carries no usable version (a rolling ``nightly``
tag, for example), so altgen can read the version from the IPA itself.
"""

from __future__ import annotations

import plistlib
import re
import zipfile
from typing import BinaryIO

# The main app bundle's Info.plist has exactly one path component between
# Payload/ and Info.plist. Extension and framework plists are nested
# deeper and must not win.
MAIN_INFO_RE = re.compile(r"^Payload/[^/]+\.app/Info\.plist$")

# Guard against a crafted archive whose plist would decompress to an
# unreasonable size; a real Info.plist is a few kilobytes.
MAX_INFO_PLIST_SIZE = 1_000_000


def read_ipa_version(stream: BinaryIO) -> str:
    """Return the app version from an IPA's main ``Info.plist``.

    Prefers ``CFBundleShortVersionString`` and falls back to
    ``CFBundleVersion``. Returns ``""`` when the archive is unreadable or
    has no usable main app Info.plist, so callers can fall back to the
    tag-derived version.
    """
    try:
        with zipfile.ZipFile(stream) as archive:
            info_name = _main_info_plist(archive)
            if info_name is None:
                return ""
            if archive.getinfo(info_name).file_size > MAX_INFO_PLIST_SIZE:
                return ""
            info = plistlib.loads(archive.read(info_name))
    except Exception:
        # A broken or hostile archive must never abort a source build;
        # callers treat "" as "fall back to the release tag".
        return ""

    version = info.get("CFBundleShortVersionString") or info.get(
        "CFBundleVersion"
    )
    if isinstance(version, str) and version.strip():
        return version.strip()
    return ""


def _main_info_plist(archive: zipfile.ZipFile) -> str | None:
    """The archive member holding the main app bundle's Info.plist."""
    for name in archive.namelist():
        if MAIN_INFO_RE.match(name):
            return name
    return None
