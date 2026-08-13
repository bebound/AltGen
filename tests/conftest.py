"""Shared factories and helpers for altgen tests."""

import json
from pathlib import Path

import pytest

from altgen.config import (
    AltgenConfig,
    AppConfig,
    GitHubConfig,
    NewsConfig,
    OutputConfig,
    SourceConfig,
    VersionsConfig,
)

FIXTURES = Path(__file__).parent / "fixtures"


def make_release(
    tag="v1.2.3",
    name="Release 1.2.3",
    body="Some changes",
    published="2024-01-01T00:00:00Z",
    draft=False,
    prerelease=False,
    assets=None,
):
    # Defaults to one matching IPA asset; pass assets=[...] to override.
    if assets is None:
        assets = [make_ipa_asset()]
    return {
        "tag_name": tag,
        "name": name,
        "body": body,
        "published_at": published,
        "draft": draft,
        "prerelease": prerelease,
        "assets": assets,
    }


def make_asset(name="App_ios_1.2.3+45.ipa", size=12345, url=None):
    return {
        "name": name,
        "size": size,
        "browser_download_url": url or f"https://example.com/dl/{name}",
    }


def make_ipa_asset(version="1.2.3", build="45", size=12345):
    return make_asset(f"App_ios_{version}+{build}.ipa", size=size)


def make_config(**overrides) -> AltgenConfig:
    """AltgenConfig with sensible defaults for unit tests."""
    kwargs = dict(
        github=GitHubConfig(repo="owner/App"),
        source=SourceConfig(name="App"),
        app=AppConfig(name="App", bundle_identifier="com.owner.app"),
        versions=VersionsConfig(),
        news=NewsConfig(),
        output=OutputConfig(),
        config_dir=Path("."),
    )
    kwargs.update(overrides)
    return AltgenConfig(**kwargs)


def write_config(tmp_path, text, name="app.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def piliplus_releases():
    return json.loads((FIXTURES / "piliplus_releases.json").read_text())


@pytest.fixture
def piliplus_expected():
    return (FIXTURES / "piliplus_expected.json").read_text(encoding="utf-8")
