"""Tests for altgen.cli."""

import json
from pathlib import Path

import pytest

from altgen import __version__
from altgen.cli import main
from altgen.github import GithubError

from conftest import make_release, write_config

MINIMAL_TOML = """
[github]
repo = "owner/App"

[app]
name = "App"
bundle_identifier = "com.owner.app"
"""


@pytest.fixture
def run(monkeypatch, capsys):
    """Run main() with fetch_releases patched to ``releases`` (or a callable)."""

    def _run(argv, releases=(), cwd=None):
        if cwd is not None:
            monkeypatch.chdir(cwd)
        captured = {}

        def fake_fetch(repo, token=None, **kwargs):
            captured["repo"] = repo
            captured["token"] = token
            return list(releases() if callable(releases) else releases)

        monkeypatch.setattr("altgen.cli.fetch_releases", fake_fetch)
        code = main(argv)
        out, err = capsys.readouterr()
        return code, out, err, captured

    return _run


def test_help_exits_zero(capsys):
    assert main(["--help"]) == 0
    assert "usage: altgen" in capsys.readouterr().out


def test_version_flag(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"altgen {__version__}"


def test_requires_config_or_cli_args(capsys):
    assert main([]) == 2
    assert "either -c/--config" in capsys.readouterr().err


def test_missing_config_file(capsys):
    assert main(["-c", "/nonexistent/app.toml"]) == 2
    assert "not found" in capsys.readouterr().err


def test_invalid_config_exits_2(tmp_path, capsys):
    config = write_config(tmp_path, "[github]\nrepo = \"no-slash\"\n")
    assert main(["-c", str(config)]) == 2
    assert "owner/name" in capsys.readouterr().err


def test_pure_cli_mode_writes_valid_json(tmp_path, run):
    release = make_release(
        tag="v1.2.3", assets=[{"name": "App_ios_1.2.3+7.ipa", "size": 100}]
    )
    out_path = tmp_path / "apps.json"
    code, out, err, captured = run(
        [
            "--repo", "owner/App",
            "--app-name", "App",
            "--bundle-id", "com.owner.app",
            "-o", str(out_path),
        ],
        releases=[release],
    )
    assert code == 0, err
    assert captured["repo"] == "owner/App"
    data = json.loads(out_path.read_text())
    assert data["name"] == "App"
    assert data["apps"][0]["bundleIdentifier"] == "com.owner.app"
    assert data["apps"][0]["developerName"] == "owner"
    versions = data["apps"][0]["versions"]
    assert [v["version"] for v in versions] == ["1.2.3"]
    assert versions[0]["buildVersion"] == "7"
    assert f"Wrote {out_path}" in out


def test_cli_flag_overrides_toml(tmp_path, run):
    config = write_config(tmp_path, MINIMAL_TOML)
    code, out, err, _ = run(
        ["-c", str(config), "--name", "NewName"],
        releases=[make_release(tag="v1.0.0")],
    )
    assert code == 0, err
    data = json.loads((tmp_path / "apps.json").read_text())
    assert data["name"] == "NewName"


def test_output_flag_resolves_against_cwd(tmp_path, run):
    config = write_config(tmp_path, MINIMAL_TOML)
    code, out, err, _ = run(
        ["-c", str(config), "-o", "nested/apps.json"],
        releases=[make_release(tag="v1.0.0")],
        cwd=tmp_path,
    )
    assert code == 0, err
    assert (tmp_path / "nested" / "apps.json").exists()


def test_toml_output_resolves_against_config_dir(tmp_path, run, monkeypatch):
    sub = tmp_path / "sources"
    sub.mkdir()
    config = write_config(
        sub, MINIMAL_TOML + '\n[output]\npath = "out/apps.json"\n'
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    code, out, err, _ = run(
        ["-c", str(config)], releases=[make_release(tag="v1.0.0")], cwd=elsewhere
    )
    assert code == 0, err
    assert (sub / "out" / "apps.json").exists()
    assert not (elsewhere / "out" / "apps.json").exists()


def test_empty_releases_exit_zero_with_warning(tmp_path, run):
    code, out, err, _ = run(
        [
            "--repo", "owner/App",
            "--app-name", "App",
            "--bundle-id", "com.owner.app",
            "-o", str(tmp_path / "apps.json"),
        ],
        releases=[],
    )
    assert code == 0
    assert "warning: no matching releases" in err
    data = json.loads((tmp_path / "apps.json").read_text())
    assert data["apps"][0]["versions"] == []


def test_github_error_exits_1(monkeypatch, capsys):
    def boom(repo, token=None):
        raise GithubError("repository not found or private: x/y (404)")

    monkeypatch.setattr("altgen.cli.fetch_releases", boom)
    code = main(
        [
            "--repo", "x/y",
            "--app-name", "App",
            "--bundle-id", "com.a",
            "-o", "/tmp/whatever.json",
        ]
    )
    assert code == 1
    assert "not found or private" in capsys.readouterr().err


def test_token_precedence_cli_over_env_over_toml(tmp_path, run, monkeypatch):
    config = write_config(
        tmp_path,
        """
[github]
repo = "owner/App"
token = "toml-token"

[app]
name = "App"
bundle_identifier = "com.owner.app"
""",
    )
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    # --token wins over env and TOML
    _, _, _, captured = run(
        ["-c", str(config), "--token", "cli-token"],
        releases=[make_release(tag="v1.0.0")],
    )
    assert captured["token"] == "cli-token"

    # env wins over TOML
    _, _, _, captured = run(["-c", str(config)], releases=[make_release(tag="v1.0.0")])
    assert captured["token"] == "env-token"

    # TOML used when env is unset
    monkeypatch.delenv("GITHUB_TOKEN")
    _, _, _, captured = run(["-c", str(config)], releases=[make_release(tag="v1.0.0")])
    assert captured["token"] == "toml-token"


def test_quiet_suppresses_success_message(tmp_path, run):
    code, out, err, _ = run(
        [
            "--repo", "owner/App",
            "--app-name", "App",
            "--bundle-id", "com.owner.app",
            "-o", str(tmp_path / "apps.json"),
            "-q",
        ],
        releases=[make_release(tag="v1.0.0")],
    )
    assert code == 0
    assert out == ""
    assert (tmp_path / "apps.json").exists()


def test_verbose_logs_skipped_releases(tmp_path, run):
    code, out, err, _ = run(
        [
            "--repo", "owner/App",
            "--app-name", "App",
            "--bundle-id", "com.owner.app",
            "-o", str(tmp_path / "apps.json"),
            "-v",
        ],
        releases=[
            make_release(tag="v9.0.0", draft=True),
            make_release(tag="v8.0.0", prerelease=True),
            make_release(tag="v7.0.0", assets=[]),
            make_release(tag="v1.0.0"),
        ],
    )
    assert code == 0
    assert "skip v9.0.0: draft" in err
    assert "skip v8.0.0: prerelease" in err
    assert "skip v7.0.0: no matching assets" in err


def test_include_prereleases_flag(tmp_path, run):
    code, out, err, _ = run(
        [
            "--repo", "owner/App",
            "--app-name", "App",
            "--bundle-id", "com.owner.app",
            "-o", str(tmp_path / "apps.json"),
            "--include-prereleases",
        ],
        releases=[
            make_release(tag="v2.0.0", prerelease=True),
            make_release(tag="v1.0.0"),
        ],
    )
    assert code == 0, err
    data = json.loads((tmp_path / "apps.json").read_text())
    assert [v["version"] for v in data["apps"][0]["versions"]] == ["2.0.0", "1.0.0"]


def test_max_versions_flag(tmp_path, run):
    code, out, err, _ = run(
        [
            "--repo", "owner/App",
            "--app-name", "App",
            "--bundle-id", "com.owner.app",
            "-o", str(tmp_path / "apps.json"),
            "--max-versions", "1",
        ],
        releases=[
            make_release(tag="v1.0.0", published="2024-01-01T00:00:00Z"),
            make_release(tag="v2.0.0", published="2024-02-01T00:00:00Z"),
        ],
    )
    assert code == 0, err
    data = json.loads((tmp_path / "apps.json").read_text())
    assert [v["version"] for v in data["apps"][0]["versions"]] == ["2.0.0"]


def test_invalid_tint_via_cli_exits_2(capsys):
    assert (
        main(
            [
                "--repo", "owner/App",
                "--app-name", "App",
                "--bundle-id", "com.a",
                "--tint-color", "notacolor",
                "-o", "/tmp/x.json",
            ]
        )
        == 2
    )
    assert "#RRGGBB" in capsys.readouterr().err
