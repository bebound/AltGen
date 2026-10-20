"""Tests for altgen.github."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from altgen.github import GithubError, fetch_ipa_version, fetch_releases

from conftest import make_ipa_bytes


def paged_response(pages, headers=None):
    """Build a fake requests.get that serves ``pages`` one at a time,
    linking to the next until exhausted."""
    responses = []
    for i, page in enumerate(pages):
        links = {}
        if i + 1 < len(pages):
            links["next"] = {"url": f"https://api.github.com/page/{i + 2}"}
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = page
        resp.links = links
        resp.status_code = 200
        resp.text = ""
        if headers:
            resp.headers = headers
        responses.append(resp)
    return MagicMock(side_effect=responses)


def test_paginates_via_link_header():
    page1 = [{"tag_name": "v1.0.0"}]
    page2 = [{"tag_name": "v0.9.0"}]
    with patch("altgen.github.requests.get", paged_response([page1, page2])) as get:
        releases = fetch_releases("owner/App")
    assert releases == page1 + page2
    assert get.call_count == 2
    # second call follows the "next" URL, not the original
    assert get.call_args_list[1].args[0] == "https://api.github.com/page/2"


def test_stops_without_next_link():
    with patch("altgen.github.requests.get", paged_response([[{"tag": "v1"}]])):
        releases = fetch_releases("owner/App")
    assert len(releases) == 1


def test_sends_bearer_header_only_with_token():
    with patch("altgen.github.requests.get", paged_response([[]])) as get:
        fetch_releases("owner/App", token="secret")
    headers = get.call_args_list[0].kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret"
    assert "User-Agent" in headers and headers["User-Agent"].startswith("altgen/")

    with patch("altgen.github.requests.get", paged_response([[]])) as get:
        fetch_releases("owner/App")
    headers = get.call_args_list[0].kwargs["headers"]
    assert "Authorization" not in headers


def test_404_friendly_error():
    resp = MagicMock()
    resp.ok = False
    resp.status_code = 404
    resp.text = "Not Found"
    resp.headers = {}
    with patch("altgen.github.requests.get", return_value=resp):
        with pytest.raises(GithubError, match=r"not found or private: owner/App"):
            fetch_releases("owner/App")


def test_403_rate_limit_friendly_error():
    resp = MagicMock()
    resp.ok = False
    resp.status_code = 403
    resp.text = "API rate limit exceeded"
    resp.headers = {"X-RateLimit-Remaining": "0"}
    with patch("altgen.github.requests.get", return_value=resp):
        with pytest.raises(GithubError, match="GITHUB_TOKEN"):
            fetch_releases("owner/App")


def test_401_friendly_error():
    resp = MagicMock()
    resp.ok = False
    resp.status_code = 401
    resp.text = "Bad credentials"
    resp.headers = {}
    with patch("altgen.github.requests.get", return_value=resp):
        with pytest.raises(GithubError, match="bad credentials"):
            fetch_releases("owner/App")


def test_other_status_error_includes_body_snippet():
    resp = MagicMock()
    resp.ok = False
    resp.status_code = 500
    resp.text = "boom " * 100
    resp.headers = {}
    with patch("altgen.github.requests.get", return_value=resp):
        with pytest.raises(GithubError, match="GitHub API error 500"):
            fetch_releases("owner/App")


def test_connection_error_friendly_message():
    with patch(
        "altgen.github.requests.get",
        side_effect=requests.ConnectionError("refused"),
    ):
        with pytest.raises(GithubError, match="network"):
            fetch_releases("owner/App")


# ---------------------------------------------------------------------------
# IPA asset download (version_source = "ipa")
# ---------------------------------------------------------------------------

def download_response(content, *, ok=True, status=200):
    resp = MagicMock()
    resp.ok = ok
    resp.status_code = status
    resp.iter_content.return_value = [content]
    return resp


def test_fetch_ipa_version_streams_asset():
    ipa = make_ipa_bytes({"CFBundleShortVersionString": "3.8.11"})
    with patch(
        "altgen.github.requests.get", return_value=download_response(ipa)
    ) as get:
        version = fetch_ipa_version("https://example.com/App.ipa")
    assert version == "3.8.11"
    assert get.call_args.kwargs["stream"] is True
    assert get.call_args.args[0] == "https://example.com/App.ipa"
    get.return_value.close.assert_called_once()


def test_fetch_ipa_version_sends_bearer_header_only_with_token():
    ipa = make_ipa_bytes({"CFBundleShortVersionString": "1.0.0"})
    with patch(
        "altgen.github.requests.get", return_value=download_response(ipa)
    ) as get:
        fetch_ipa_version("https://example.com/App.ipa", token="secret")
    headers = get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret"
    assert headers["User-Agent"].startswith("altgen/")


def test_fetch_ipa_version_http_error():
    resp = download_response(b"", ok=False, status=500)
    with patch("altgen.github.requests.get", return_value=resp):
        with pytest.raises(GithubError, match=r"cannot download .* HTTP 500"):
            fetch_ipa_version("https://example.com/App.ipa")


def test_fetch_ipa_version_connection_error():
    with patch(
        "altgen.github.requests.get",
        side_effect=requests.ConnectionError("refused"),
    ):
        with pytest.raises(GithubError, match="cannot download"):
            fetch_ipa_version("https://example.com/App.ipa")


def test_fetch_ipa_version_stream_error():
    resp = download_response(b"")
    resp.iter_content.side_effect = requests.ConnectionError("reset")
    with patch("altgen.github.requests.get", return_value=resp):
        with pytest.raises(GithubError, match="cannot download"):
            fetch_ipa_version("https://example.com/App.ipa")


def test_fetch_ipa_version_unreadable_archive_returns_empty():
    with patch(
        "altgen.github.requests.get",
        return_value=download_response(b"not a zip"),
    ):
        assert fetch_ipa_version("https://example.com/App.ipa") == ""
