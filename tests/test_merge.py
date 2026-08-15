"""Tests for altgen.merge (merge_sources + the ``altgen merge`` CLI)."""

import json

import pytest

from altgen.cli import main
from altgen.config import SourceConfig
from altgen.merge import MergeError, merge_sources

from conftest import write_config


def make_doc(apps=None, news=None, root=None):
    doc = {"name": "Source", "apps": apps or []}
    if news is not None:
        doc["news"] = news
    doc.update(root or {})
    return doc


def make_app(bundle_id="com.x.y", name="App", news=None, versions=None):
    app = {
        "name": name,
        "bundleIdentifier": bundle_id,
        "versions": versions if versions is not None else [{"version": "1.0"}],
    }
    if news is not None:
        app["news"] = news
    return app


def make_news(identifier="release-1.0.0", date="2024-01-01T00:00:00Z"):
    return {"identifier": identifier, "date": date, "title": "App 1.0.0"}


SOURCE = SourceConfig(name="Merged", subtitle="Sub", description="Desc")


def write_doc(tmp_path, name, doc):
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# merge_sources
# ---------------------------------------------------------------------------

def test_merge_basic_key_order_and_collection():
    doc1 = make_doc(
        apps=[make_app(bundle_id="com.a", news=[make_news("r1", "2024-01-01T00:00:00Z")])],
        news=[make_news("r2", "2024-02-01T00:00:00Z")],
    )
    doc2 = make_doc(apps=[make_app(bundle_id="com.b")])
    data = merge_sources([("a.json", doc1), ("b.json", doc2)], SOURCE)
    # root values come from the config, not from the input documents
    assert list(data.keys()) == ["name", "subtitle", "description", "apps", "news"]
    assert data["name"] == "Merged"
    assert data["subtitle"] == "Sub"
    # apps keep input order
    assert [a["bundleIdentifier"] for a in data["apps"]] == ["com.a", "com.b"]
    # news gathered from root + app levels, sorted newest first
    assert [n["identifier"] for n in data["news"]] == ["r2", "r1"]


def test_merge_root_optionals():
    src = SourceConfig(
        name="M",
        icon_url="https://e.com/i.png",
        website="https://e.com",
        tint_color="#00AEEF",
    )
    data = merge_sources([("a.json", make_doc(apps=[make_app()]))], src)
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
    assert data["iconURL"] == "https://e.com/i.png"


def test_merge_duplicate_bundle_identifier():
    doc1 = make_doc(apps=[make_app(bundle_id="com.x")])
    doc2 = make_doc(apps=[make_app(bundle_id="com.x")])
    with pytest.raises(
        MergeError, match=r"duplicate bundleIdentifier com\.x in a\.json and b\.json"
    ):
        merge_sources([("a.json", doc1), ("b.json", doc2)], SOURCE)


def test_merge_duplicate_news_identifier():
    doc1 = make_doc(apps=[make_app(bundle_id="com.a", news=[make_news()])])
    doc2 = make_doc(apps=[make_app(bundle_id="com.b", news=[make_news()])])
    with pytest.raises(
        MergeError,
        match=r"duplicate news identifier release-1\.0\.0 in a\.json and b\.json",
    ):
        merge_sources([("a.json", doc1), ("b.json", doc2)], SOURCE)


def test_merge_invalid_documents():
    with pytest.raises(MergeError, match="not a JSON object"):
        merge_sources([("a.json", [])], SOURCE)
    with pytest.raises(MergeError, match="missing 'apps' list"):
        merge_sources([("a.json", {"name": "x"})], SOURCE)
    with pytest.raises(MergeError, match="missing 'apps' list"):
        merge_sources([("a.json", {"apps": "nope"})], SOURCE)


def test_merge_app_without_bundle_identifier():
    doc = make_doc(apps=[{"name": "App", "versions": []}])
    with pytest.raises(MergeError, match="app without bundleIdentifier"):
        merge_sources([("a.json", doc)], SOURCE)


def test_merge_news_without_identifier():
    doc = make_doc(apps=[make_app(bundle_id="com.a", news=[{"date": "2024-01-01"}])])
    with pytest.raises(MergeError, match="news entry without identifier"):
        merge_sources([("a.json", doc)], SOURCE)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_merge_writes_merged_source(tmp_path, capsys):
    f1 = write_doc(
        tmp_path, "a.json",
        make_doc(apps=[make_app(bundle_id="com.a")], news=[make_news("r1", "2024-01-01T00:00:00Z")]),
    )
    f2 = write_doc(
        tmp_path, "b.json",
        make_doc(apps=[make_app(bundle_id="com.b")], news=[make_news("r2", "2024-02-01T00:00:00Z")]),
    )
    out = tmp_path / "merged.json"
    code = main(
        [
            "merge", str(f1), str(f2),
            "--name", "Merged",
            "--tint-color", "#00AEEF",
            "-o", str(out),
        ]
    )
    assert code == 0
    data = json.loads(out.read_text())
    assert data["name"] == "Merged"
    assert data["tintColor"] == "#00AEEF"
    assert [a["bundleIdentifier"] for a in data["apps"]] == ["com.a", "com.b"]
    assert [n["identifier"] for n in data["news"]] == ["r2", "r1"]
    assert "Wrote" in capsys.readouterr().out


def test_cli_merge_requires_name(tmp_path, capsys):
    f1 = write_doc(tmp_path, "a.json", make_doc(apps=[make_app()]))
    assert main(["merge", str(f1)]) == 2
    assert "--name" in capsys.readouterr().err


def test_cli_merge_invalid_tint_exits_2(tmp_path, capsys):
    f1 = write_doc(tmp_path, "a.json", make_doc(apps=[make_app()]))
    assert main(["merge", str(f1), "--name", "M", "--tint-color", "blue"]) == 2
    assert "#RRGGBB" in capsys.readouterr().err


def test_cli_merge_config_and_cli_override(tmp_path, capsys):
    f1 = write_doc(tmp_path, "a.json", make_doc(apps=[make_app()]))
    config = write_config(
        tmp_path,
        """
[source]
name = "FromToml"
subtitle = "Toml subtitle"

[output]
path = "out/merged.json"
""",
    )
    code = main(["merge", "-c", str(config), str(f1), "--name", "FromCli"])
    assert code == 0
    data = json.loads((tmp_path / "out" / "merged.json").read_text())
    assert data["name"] == "FromCli"
    assert data["subtitle"] == "Toml subtitle"


def test_cli_merge_invalid_json_exits_2(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert main(["merge", str(bad), "--name", "M"]) == 2
    assert "invalid JSON" in capsys.readouterr().err


def test_cli_merge_unreadable_file_exits_1(tmp_path, capsys):
    assert main(["merge", str(tmp_path / "missing.json"), "--name", "M"]) == 1
    assert "cannot read" in capsys.readouterr().err


def test_cli_merge_duplicate_apps_exit_2(tmp_path, capsys):
    f1 = write_doc(tmp_path, "a.json", make_doc(apps=[make_app(bundle_id="com.x")]))
    f2 = write_doc(tmp_path, "b.json", make_doc(apps=[make_app(bundle_id="com.x")]))
    assert main(["merge", str(f1), str(f2), "--name", "M"]) == 2
    assert "duplicate bundleIdentifier" in capsys.readouterr().err


def test_cli_merge_quiet(tmp_path, capsys):
    f1 = write_doc(tmp_path, "a.json", make_doc(apps=[make_app()]))
    assert main(["merge", str(f1), "--name", "M", "-q"]) == 0
    assert capsys.readouterr().out == ""
