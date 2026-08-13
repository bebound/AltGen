"""Tests for altgen.source."""

import re

from altgen.config import AppConfig, NewsConfig, SourceConfig, VersionsConfig
from altgen.source import (
    build_news_entry,
    build_source,
    build_version_entry,
    extract_build_version,
    serialize,
    short_date,
    version_from_tag,
)

from conftest import make_asset, make_config, make_ipa_asset, make_release


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_version_from_tag():
    assert version_from_tag("v1.2.3", True) == "1.2.3"
    assert version_from_tag("v1.2.3", False) == "v1.2.3"
    assert version_from_tag("1.2.3", True) == "1.2.3"
    assert version_from_tag("v", True) == ""
    assert version_from_tag("", True) == ""


def test_short_date():
    assert short_date("2024-01-02T03:04:05Z") == "2024-01-02"
    assert short_date("2024-01-02T03:04:05.000Z") == "2024-01-02"
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", short_date(""))  # now() fallback


def test_extract_build_version_group_and_whole_match():
    pattern = re.compile(r"\+(\d+)\.ipa$", re.IGNORECASE)
    assert extract_build_version("App_ios_2.0.6+4915.ipa", pattern) == "4915"
    assert extract_build_version("App_ios_2.0.6.ipa", pattern) == ""
    assert extract_build_version("", pattern) == ""
    whole = re.compile(r"\d+")
    assert extract_build_version("abc123", whole) == "123"


# ---------------------------------------------------------------------------
# Version entries
# ---------------------------------------------------------------------------

def test_version_entry_key_order_with_build_version():
    cfg = make_config(app=AppConfig(name="A", bundle_identifier="b", min_os_version="14.0"))
    entry = build_version_entry(
        cfg,
        make_release(tag="v1.0.0"),
        make_ipa_asset(),
        "1.0.0",
    )
    assert list(entry.keys()) == [
        "version",
        "buildVersion",
        "date",
        "localizedDescription",
        "downloadURL",
        "size",
        "minOSVersion",
    ]
    assert entry["buildVersion"] == "45"
    assert entry["size"] == 12345


def test_version_entry_omits_build_version_and_min_os():
    cfg = make_config(app=AppConfig(name="A", bundle_identifier="b"))
    entry = build_version_entry(
        cfg,
        make_release(tag="v1.0.0"),
        make_asset("App.ipa"),
        "1.0.0",
    )
    assert list(entry.keys()) == [
        "version",
        "date",
        "localizedDescription",
        "downloadURL",
        "size",
    ]


def test_version_entry_description_fallback_chain():
    app = AppConfig(name="A", bundle_identifier="b", description="Fallback text")
    cfg = make_config(app=app)
    release = make_release(body="  Actual body  ")
    entry = build_version_entry(cfg, release, make_ipa_asset(), "1.0.0")
    assert entry["localizedDescription"] == "Actual body"

    release = make_release(body="   ")
    entry = build_version_entry(cfg, release, make_ipa_asset(), "1.0.0")
    assert entry["localizedDescription"] == "Fallback text"

    cfg = make_config(app=AppConfig(name="A", bundle_identifier="b"))
    entry = build_version_entry(cfg, release, make_ipa_asset(), "1.0.0")
    assert entry["localizedDescription"] == ""


# ---------------------------------------------------------------------------
# Source building
# ---------------------------------------------------------------------------

def test_source_skeleton_key_order_and_optionals():
    cfg = make_config(
        source=SourceConfig(
            name="Src",
            subtitle="Sub",
            description="Desc",
            icon_url="https://e.com/icon.png",
            website="https://e.com",
            tint_color="#ABCDEF",
        ),
        app=AppConfig(
            name="App",
            bundle_identifier="com.x.y",
            icon_url="https://e.com/icon.png",
            screenshots=("https://e.com/s1.png",),
            tint_color="#ABCDEF",
        ),
    )
    data = build_source(cfg, [])
    assert list(data.keys()) == [
        "name",
        "subtitle",
        "description",
        "iconURL",
        "website",
        "tintColor",
        "apps",
        "news",
    ]
    app = data["apps"][0]
    assert list(app.keys()) == [
        "name",
        "bundleIdentifier",
        "developerName",
        "subtitle",
        "localizedDescription",
        "iconURL",
        "screenshots",
        "tintColor",
        "versions",
        "news",
    ]


def test_source_omits_unset_optionals():
    cfg = make_config(
        app=AppConfig(
            name="A",
            bundle_identifier="b",
            icon_url="https://e.com/i.png",
            screenshots=(),
            tint_color=None,
        ),
    )
    data = build_source(cfg, [])
    assert "iconURL" not in data
    assert "website" not in data
    assert "tintColor" not in data
    app = data["apps"][0]
    assert "screenshots" not in app
    assert "tintColor" not in app


def test_drafts_and_prereleases_skipped():
    cfg = make_config()
    releases = [
        make_release(tag="v3.0.0", draft=True),
        make_release(tag="v2.0.0", prerelease=True),
        make_release(tag="v1.0.0"),
    ]
    data = build_source(cfg, releases)
    assert [v["version"] for v in data["apps"][0]["versions"]] == ["1.0.0"]
    assert [n["identifier"] for n in data["news"]] == ["release-1.0.0"]


def test_prereleases_included_when_configured():
    cfg = make_config(versions=VersionsConfig(include_prereleases=True))
    releases = [
        make_release(tag="v2.0.0", prerelease=True),
        make_release(tag="v1.0.0"),
    ]
    data = build_source(cfg, releases)
    assert [v["version"] for v in data["apps"][0]["versions"]] == [
        "2.0.0",
        "1.0.0",
    ]


def test_release_without_ipa_is_skipped_including_news():
    cfg = make_config()
    releases = [
        make_release(tag="v1.0.0", assets=[make_asset("App.apk")]),
        make_release(tag="v0.9.0", assets=[]),
    ]
    data = build_source(cfg, releases)
    assert data["apps"][0]["versions"] == []
    assert data["news"] == []


def test_empty_tag_skipped():
    cfg = make_config()
    data = build_source(cfg, [make_release(tag="v")])
    assert data["apps"][0]["versions"] == []


def test_multiple_ipas_yield_multiple_versions_single_news():
    cfg = make_config()
    release = make_release(
        tag="v1.0.0",
        assets=[make_ipa_asset(build="1"), make_ipa_asset(build="2")],
    )
    data = build_source(cfg, [release])
    versions = data["apps"][0]["versions"]
    assert [v["buildVersion"] for v in versions] == ["1", "2"]
    assert len(data["news"]) == 1


def test_versions_sorted_by_date_then_version_desc():
    cfg = make_config()
    releases = [
        make_release(tag="v2.9.0", published="2024-01-02T00:00:00Z"),
        make_release(tag="v2.10.0", published="2024-01-01T00:00:00Z"),
    ]
    data = build_source(cfg, releases)
    assert [v["version"] for v in data["apps"][0]["versions"]] == [
        "2.9.0",
        "2.10.0",
    ]


def test_news_sorted_by_date_desc():
    cfg = make_config()
    releases = [
        make_release(tag="v1.0.0", published="2024-01-01T00:00:00Z"),
        make_release(tag="v2.0.0", published="2024-02-01T00:00:00Z"),
    ]
    data = build_source(cfg, releases)
    assert [n["identifier"] for n in data["news"]] == [
        "release-2.0.0",
        "release-1.0.0",
    ]


def test_max_versions_caps_after_sort():
    cfg = make_config(versions=VersionsConfig(max_versions=1))
    releases = [
        make_release(tag="v1.0.0", published="2024-01-01T00:00:00Z"),
        make_release(tag="v2.0.0", published="2024-02-01T00:00:00Z"),
    ]
    data = build_source(cfg, releases)
    assert [v["version"] for v in data["apps"][0]["versions"]] == ["2.0.0"]


def test_news_max_entries_caps_after_sort():
    cfg = make_config(news=NewsConfig(max_entries=1))
    releases = [
        make_release(tag="v1.0.0", published="2024-01-01T00:00:00Z"),
        make_release(tag="v2.0.0", published="2024-02-01T00:00:00Z"),
    ]
    data = build_source(cfg, releases)
    assert [n["identifier"] for n in data["news"]] == ["release-2.0.0"]


def test_news_disabled():
    cfg = make_config(news=NewsConfig(enabled=False))
    data = build_source(cfg, [make_release(tag="v1.0.0")])
    assert data["news"] == []


def test_news_entry_fields_and_template():
    cfg = make_config(
        app=AppConfig(
            name="MyApp",
            bundle_identifier="com.x.y",
            tint_color="#123456",
        ),
        news=NewsConfig(title_template="{name} — {version}!"),
    )
    release = make_release(tag="v1.0.0", name="Big release")
    entry = build_news_entry(cfg, release, "1.0.0", "v1.0.0")
    assert list(entry.keys()) == [
        "title",
        "identifier",
        "caption",
        "date",
        "tintColor",
        "notify",
        "appID",
        "url",
    ]
    assert entry["title"] == "MyApp — 1.0.0!"
    assert entry["caption"] == "Big release"
    assert entry["url"] == "https://github.com/owner/App/releases/tag/v1.0.0"
    assert entry["appID"] == "com.x.y"

    # caption falls back when release name is missing; tintColor omitted when unset
    cfg = make_config()
    release = make_release(tag="v1.0.0", name=None)
    entry = build_news_entry(cfg, release, "1.0.0", "v1.0.0")
    assert entry["caption"] == "Version 1.0.0 released"
    assert "tintColor" not in entry


def test_custom_asset_pattern():
    cfg = make_config(versions=VersionsConfig(asset_pattern=r"ios.*\.ipa$"))
    release = make_release(
        tag="v1.0.0",
        assets=[make_asset("MyApp_ios_1.0.0.ipa"), make_asset("MyApp_android.apk")],
    )
    data = build_source(cfg, [release])
    assert len(data["apps"][0]["versions"]) == 1


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_serialize_indent_unicode_and_trailing_newline():
    text = serialize({"name": "テスト", "apps": []})
    assert text.endswith("\n")
    assert "テスト" in text  # ensure_ascii=False
    assert "\n  " in text  # indent=2
