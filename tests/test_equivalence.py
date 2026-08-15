"""Byte-for-byte equivalence for the example config, offline.

Fixtures were captured from the PiliPlus release data; the example config
relies on the default max_versions = 1 (newest version only), so the
expected apps.json contains a single version entry and its single news
entry.
"""

from pathlib import Path

from altgen.config import load_config
from altgen.source import build_source, serialize

EXAMPLE = Path(__file__).parent.parent / "examples" / "piliplus.toml"


def test_piliplus_byte_equivalence(piliplus_releases, piliplus_expected):
    config = load_config(EXAMPLE)
    data = build_source(config, piliplus_releases)
    assert serialize(data) == piliplus_expected
