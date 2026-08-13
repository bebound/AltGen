"""Byte-for-byte equivalence with the original update_source.py output.

Both fixtures were captured from the same PiliPlus release data: the new
pipeline must reproduce the old script's apps.json exactly, offline.
"""

from pathlib import Path

from altgen.config import load_config
from altgen.source import build_source, serialize

EXAMPLE = Path(__file__).parent.parent / "examples" / "piliplus.toml"


def test_piliplus_byte_equivalence(piliplus_releases, piliplus_expected):
    config = load_config(EXAMPLE)
    data = build_source(config, piliplus_releases)
    assert serialize(data) == piliplus_expected
