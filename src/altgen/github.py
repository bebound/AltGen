"""GitHub Releases API client for altgen."""

from __future__ import annotations

import requests

from altgen import __version__

API_ROOT = "https://api.github.com"

MAX_PAGES = 100  # safety cap against a malformed pagination chain


class GithubError(RuntimeError):
    """GitHub API failure with a human-friendly message."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def fetch_releases(
    repo: str, token: str | None = None, *, per_page: int = 100
) -> list[dict]:
    """Return all releases of ``repo`` (``owner/name``), paginating via the
    Link header.

    Raises :class:`GithubError` on API errors, rate limiting, or
    connection problems. Unauthenticated requests are limited to 60 per
    hour; pass a token to get 5,000.
    """
    releases: list[dict] = []
    url: str | None = f"{API_ROOT}/repos/{repo}/releases?per_page={per_page}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"altgen/{__version__}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    pages = 0
    while url:
        pages += 1
        if pages > MAX_PAGES:
            raise GithubError(
                f"stopped after {MAX_PAGES} pages of releases for {repo}; "
                "the pagination chain looks malformed"
            )
        try:
            resp = requests.get(url, headers=headers, timeout=30)
        except requests.RequestException as exc:
            raise GithubError(
                f"cannot reach GitHub API for {repo}: {exc}. "
                "Check your network connection and retry."
            ) from exc
        if not resp.ok:
            raise _friendly_error(repo, resp)

        releases.extend(resp.json())
        url = resp.links.get("next", {}).get("url")

    return releases


def _friendly_error(repo: str, resp) -> GithubError:
    status = resp.status_code
    body = resp.text or ""
    remaining = resp.headers.get("X-RateLimit-Remaining")

    if status == 403 and (remaining == "0" or "rate limit" in body.lower()):
        return GithubError(
            "GitHub API rate limit exceeded "
            "(unauthenticated: 60 requests/hour). "
            "Set GITHUB_TOKEN or pass --token to raise the limit to "
            "5,000 requests/hour.",
            status=status,
        )
    if status == 404:
        return GithubError(
            f"repository not found or private: {repo} (404)", status=status
        )
    if status == 401:
        return GithubError(
            "bad credentials (401) — check --token / GITHUB_TOKEN", status=status
        )
    detail = body[:200].replace("\n", " ")
    return GithubError(
        f"GitHub API error {status} for {repo}: {detail}", status=status
    )
