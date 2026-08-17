"""Tests for altgen.config."""

from pathlib import Path

import argparse

import pytest

from conftest import write_config

from altgen.config import (
    AltgenConfig,
    ConfigError,
    apply_cli_overrides,
    default_config,
    load_config,
    load_merge_config,
)

MINIMAL_TOML = """
[github]
repo = "owner/App"

[app]
name = "App"
bundle_identifier = "com.owner.app"
"""


def test_minimal_config_defaults(tmp_path):
    config = load_config(write_config(tmp_path, MINIMAL_TOML))
    assert config.github.repo == "owner/App"
    assert config.github.token is None
    assert config.source.name == "App"  # defaults to repo short name
    assert config.app.name == "App"
    assert config.versions.strip_v_prefix is True
    assert config.versions.include_prereleases is False
    assert config.versions.version_pattern is None  # version from tag
    assert config.versions.version_source == "release"
    assert config.versions.max_versions == 1  # default: latest version only
    assert config.news.enabled is True
    assert config.news.max_entries is None
    assert config.news.title_template == "{name} {version} - {date}"
    assert config.news.caption_template == "{name} {version} is available."
    assert config.news.image_url is None
    assert config.output.path == (tmp_path / "apps.json").resolve()


@pytest.mark.parametrize(
    "toml, message",
    [
        (
            """
            [app]
            name = "App"
            bundle_identifier = "com.owner.app"
            """,
            r"\[github\] repo is required",
        ),
        (
            """
            [github]
            repo = "owner/App"

            [app]
            bundle_identifier = "com.owner.app"
            """,
            r"\[app\] name is required",
        ),
        (
            """
            [github]
            repo = "owner/App"

            [app]
            name = "App"
            """,
            r"\[app\] bundle_identifier is required",
        ),
    ],
)
def test_required_keys(tmp_path, toml, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write_config(tmp_path, toml))


def test_unknown_key_rejected(tmp_path):
    toml = MINIMAL_TOML + 'badkey = true\n'
    with pytest.raises(ConfigError, match=r"\[app\] unknown key 'badkey'"):
        load_config(write_config(tmp_path, toml))


def test_camelcase_key_rejected(tmp_path):
    """bundleIdentifier (camelCase) must error, not silently vanish."""
    toml = """
    [github]
    repo = "owner/App"

    [app]
    name = "App"
    bundleIdentifier = "com.owner.app"
    """
    with pytest.raises(ConfigError, match="unknown key 'bundleIdentifier'"):
        load_config(write_config(tmp_path, toml))


def test_merge_config_minimal(tmp_path):
    toml = """
[source]
name = "Merged"
subtitle = "All apps"
tint_color = "#00AEEF"

[output]
path = "out/merged.json"
"""
    config = load_merge_config(write_config(tmp_path, toml))
    assert config.source.name == "Merged"
    assert config.source.subtitle == "All apps"
    assert config.source.tint_color == "#00AEEF"
    assert config.source.icon_url is None
    assert config.output.path == (tmp_path / "out" / "merged.json").resolve()
    assert config.config_dir == tmp_path.resolve()


def test_merge_config_rejects_build_tables(tmp_path):
    toml = """
[github]
repo = "owner/App"

[source]
name = "Merged"
"""
    with pytest.raises(ConfigError, match=r"only supports \[source\] and \[output\]"):
        load_merge_config(write_config(tmp_path, toml))


def test_merge_config_default_output_path(tmp_path):
    toml = '[source]\nname = "Merged"\n'
    config = load_merge_config(write_config(tmp_path, toml))
    assert config.output.path == (tmp_path / "apps.json").resolve()


def test_merge_config_unknown_source_key_rejected(tmp_path):
    toml = '[source]\nname = "Merged"\nbogus = 1\n'
    with pytest.raises(ConfigError, match=r"\[source\] unknown key 'bogus'"):
        load_merge_config(write_config(tmp_path, toml))


def test_unknown_table_rejected(tmp_path):
    toml = MINIMAL_TOML + "\n[unknown]\nfoo = 1\n"
    with pytest.raises(ConfigError, match="unknown table \\[unknown\\]"):
        load_config(write_config(tmp_path, toml))


def test_invalid_repo(tmp_path):
    toml = """
    [github]
    repo = "no-slash"

    [app]
    name = "App"
    bundle_identifier = "com.owner.app"
    """
    with pytest.raises(ConfigError, match="must be 'owner/name'"):
        load_config(write_config(tmp_path, toml))


def test_invalid_asset_pattern_regex(tmp_path):
    toml = MINIMAL_TOML + """
[versions]
asset_pattern = "("
"""
    with pytest.raises(ConfigError, match="invalid regex"):
        load_config(write_config(tmp_path, toml))


def test_invalid_tint_color(tmp_path):
    toml = MINIMAL_TOML + 'tint_color = "blue"\n'
    with pytest.raises(ConfigError, match="tint_color must be #RRGGBB"):
        load_config(write_config(tmp_path, toml))


def test_invalid_toml_syntax(tmp_path):
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(write_config(tmp_path, "this is = not toml =="))


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_negative_max_versions_rejected(tmp_path):
    toml = MINIMAL_TOML + "\n[versions]\nmax_versions = -1\n"
    with pytest.raises(ConfigError, match="max_versions must be >= 0"):
        load_config(write_config(tmp_path, toml))


def test_max_versions_zero_means_all(tmp_path):
    toml = MINIMAL_TOML + "\n[versions]\nmax_versions = 0\n"
    assert load_config(write_config(tmp_path, toml)).versions.max_versions is None


def test_max_versions_explicit_value(tmp_path):
    toml = MINIMAL_TOML + "\n[versions]\nmax_versions = 5\n"
    assert load_config(write_config(tmp_path, toml)).versions.max_versions == 5


def test_invalid_news_template_placeholder(tmp_path):
    toml = MINIMAL_TOML + '\n[news]\ntitle_template = "{name} {bogus}"\n'
    with pytest.raises(ConfigError, match="invalid placeholder"):
        load_config(write_config(tmp_path, toml))


def test_news_caption_template_and_image_url(tmp_path):
    toml = MINIMAL_TOML + """
[news]
title_template = "{name} {version} - {date}"
caption_template = "New {name} update available!"
image_url = "https://e.com/news.png"
"""
    config = load_config(write_config(tmp_path, toml))
    assert config.news.title_template == "{name} {version} - {date}"
    assert config.news.caption_template == "New {name} update available!"
    assert config.news.image_url == "https://e.com/news.png"


def test_bool_rejected_for_int(tmp_path):
    toml = MINIMAL_TOML + "\n[news]\nmax_entries = true\n"
    with pytest.raises(ConfigError, match="max_entries must be an integer"):
        load_config(write_config(tmp_path, toml))


def test_screenshots_must_be_strings(tmp_path):
    toml = MINIMAL_TOML + "screenshots = [1, 2]\n"
    with pytest.raises(ConfigError, match="screenshots must be a list of strings"):
        load_config(write_config(tmp_path, toml))


def test_output_path_resolves_against_config_dir(tmp_path):
    sub = tmp_path / "piliplus"
    sub.mkdir()
    config = load_config(
        write_config(
            sub,
            MINIMAL_TOML + "\n[output]\npath = \"out/apps.json\"\n",
        )
    )
    assert config.output.path == (sub / "out" / "apps.json").resolve()
    assert config.config_dir == sub.resolve()


def test_app_icon_and_tint_fallback_to_source(tmp_path):
    toml = """
    [github]
    repo = "owner/App"

    [source]
    name = "App"
    icon_url = "https://example.com/icon.png"
    tint_color = "#00AEEF"

    [app]
    name = "App"
    bundle_identifier = "com.owner.app"
    """
    config = load_config(write_config(tmp_path, toml))
    assert config.app.icon_url == "https://example.com/icon.png"
    assert config.app.tint_color == "#00AEEF"


def test_app_icon_explicit_wins_over_source(tmp_path):
    toml = """
    [github]
    repo = "owner/App"

    [source]
    name = "App"
    icon_url = "https://example.com/source.png"

    [app]
    name = "App"
    bundle_identifier = "com.owner.app"
    icon_url = "https://example.com/app.png"
    """
    config = load_config(write_config(tmp_path, toml))
    assert config.app.icon_url == "https://example.com/app.png"


def test_regexes_compiled():
    config = default_config("owner/App", "App", "com.owner.app")
    assert config.asset_re.search("APP.IPA") is not None
    assert config.asset_re.search("app.txt") is None
    match = config.build_re.search("App_ios_2.0.6+4915.ipa")
    assert match and match.group(1) == "4915"
    assert config.version_re is None  # no version_pattern → tag-derived


def test_version_pattern_and_source_loaded(tmp_path):
    toml = MINIMAL_TOML + """
[versions]
version_pattern = "_([0-9]+[.][0-9]+[.][0-9]+)_"
version_source = "filename"
"""
    config = load_config(write_config(tmp_path, toml))
    assert config.versions.version_pattern == "_([0-9]+[.][0-9]+[.][0-9]+)_"
    assert config.versions.version_source == "filename"
    match = config.version_re.search("YouProExtra_21.24.3_1.3.1")
    assert match and match.group(1) == "21.24.3"


def test_version_source_defaults_to_release(tmp_path):
    toml = MINIMAL_TOML + '\n[versions]\nversion_pattern = "([0-9]+[.][0-9]+)"\n'
    config = load_config(write_config(tmp_path, toml))
    assert config.versions.version_pattern == "([0-9]+[.][0-9]+)"
    assert config.versions.version_source == "release"


def test_invalid_version_pattern_regex(tmp_path):
    toml = MINIMAL_TOML + '\n[versions]\nversion_pattern = "("\n'
    with pytest.raises(ConfigError, match="invalid regex"):
        load_config(write_config(tmp_path, toml))


def test_invalid_version_source_rejected(tmp_path):
    toml = MINIMAL_TOML + '\n[versions]\nversion_source = "ipa-name"\n'
    with pytest.raises(
        ConfigError, match="version_source must be 'release' or 'filename'"
    ):
        load_config(write_config(tmp_path, toml))


def test_default_config_cli_defaults():
    config = default_config("owner/MyApp", "MyApp", "com.owner.myapp")
    assert config.source.name == "MyApp"
    assert config.source.subtitle == "Auto-updated AltStore source for MyApp"
    assert config.app.developer_name == "owner"
    assert config.app.subtitle == "Latest MyApp release"
    assert config.output.path == (Path.cwd() / "apps.json").resolve()
    assert config.app.icon_url is None
    assert config.app.tint_color is None
    assert config.versions.max_versions == 1


def test_cli_overrides_toml(tmp_path):
    config = load_config(write_config(tmp_path, MINIMAL_TOML))
    args = argparse.Namespace(
        repo=None,
        token=None,
        name="NewSource",
        subtitle=None,
        description=None,
        icon_url=None,
        website=None,
        tint_color=None,
        app_name="NewApp",
        bundle_id=None,
        developer_name="dev",
        app_subtitle=None,
        app_description=None,
        app_icon_url=None,
        app_tint_color=None,
        min_os_version="15.0",
        screenshots=None,
        include_prereleases=None,
        max_versions=5,
        output="out/apps.json",
    )
    merged = apply_cli_overrides(config, args)
    assert merged.source.name == "NewSource"
    assert merged.app.name == "NewApp"
    assert merged.app.developer_name == "dev"
    assert merged.app.min_os_version == "15.0"
    assert merged.versions.max_versions == 5
    assert merged.output.path == (Path.cwd() / "out" / "apps.json").resolve()
    # absent flags leave TOML values untouched
    assert merged.github.repo == "owner/App"
    assert merged.versions.strip_v_prefix is True


def test_cli_overrides_absent_flags_do_not_clobber(tmp_path):
    toml = MINIMAL_TOML + "\n[versions]\ninclude_prereleases = true\n"
    config = load_config(write_config(tmp_path, toml))
    args = argparse.Namespace(
        repo=None,
        token=None,
        name=None,
        subtitle=None,
        description=None,
        icon_url=None,
        website=None,
        tint_color=None,
        app_name=None,
        bundle_id=None,
        developer_name=None,
        app_subtitle=None,
        app_description=None,
        app_icon_url=None,
        app_tint_color=None,
        min_os_version=None,
        screenshots=None,
        include_prereleases=None,
        max_versions=None,
        output=None,
    )
    merged = apply_cli_overrides(config, args)
    assert merged.versions.include_prereleases is True


def test_cli_max_versions_zero_means_all():
    config = default_config("owner/App", "App", "com.owner.app")
    args = argparse.Namespace(max_versions=0)
    merged = apply_cli_overrides(config, args)
    assert merged.versions.max_versions is None
