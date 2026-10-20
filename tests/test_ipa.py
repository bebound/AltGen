"""Tests for altgen.ipa."""

import io
import plistlib

from altgen.ipa import read_ipa_version

from conftest import make_ipa_bytes


def test_reads_cf_bundle_short_version_string():
    ipa = make_ipa_bytes({"CFBundleShortVersionString": "3.8.11"})
    assert read_ipa_version(io.BytesIO(ipa)) == "3.8.11"


def test_falls_back_to_cf_bundle_version():
    ipa = make_ipa_bytes({"CFBundleVersion": "42"})
    assert read_ipa_version(io.BytesIO(ipa)) == "42"


def test_prefers_short_version_string():
    ipa = make_ipa_bytes(
        {"CFBundleShortVersionString": "3.8.11", "CFBundleVersion": "3.8.12"}
    )
    assert read_ipa_version(io.BytesIO(ipa)) == "3.8.11"


def test_ignores_nested_extension_plist():
    ipa = make_ipa_bytes(
        {"CFBundleShortVersionString": "1.2.3"},
        extra={
            "Payload/App.app/PlugIns/Widget.appex/Info.plist": plistlib.dumps(
                {"CFBundleShortVersionString": "9.9.9"}
            )
        },
    )
    assert read_ipa_version(io.BytesIO(ipa)) == "1.2.3"


def test_missing_info_plist_returns_empty():
    assert read_ipa_version(io.BytesIO(make_ipa_bytes(None))) == ""


def test_non_ipa_archive_returns_empty():
    assert read_ipa_version(io.BytesIO(b"not a zip")) == ""


def test_bad_plist_returns_empty():
    ipa = make_ipa_bytes(None, extra={"Payload/App.app/Info.plist": b"junk"})
    assert read_ipa_version(io.BytesIO(ipa)) == ""


def test_non_string_version_returns_empty():
    ipa = make_ipa_bytes({"CFBundleShortVersionString": 3811})
    assert read_ipa_version(io.BytesIO(ipa)) == ""
