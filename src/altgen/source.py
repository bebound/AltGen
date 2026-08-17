"""Build AltStore apps.json source documents — pure functions, no network.

JSON key order follows the AltStore source spec and is stable, so output
is byte-for-byte reproducible for a given config + release list.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timezone

from altgen.config import AltgenConfig


def iso_datetime(value: str) -> str:
    """Return an ISO-8601 datetime string; fall back to *now* if empty."""
    if not value:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return value.replace(".000", "")


def short_date(value: str) -> str:
    """Return only the date portion (YYYY-MM-DD) of an ISO datetime."""
    return iso_datetime(value).split("T", 1)[0]


def human_date(value: str) -> str:
    """Format the date portion of an ISO datetime as '07 Aug 2026' (for
    news title templates)."""
    return datetime.strptime(short_date(value), "%Y-%m-%d").strftime(
        "%d %b %Y"
    )


def version_from_tag(tag: str, strip_v_prefix: bool) -> str:
    """Release tag minus a leading ``v`` (when configured); ``""`` for
    an empty tag."""
    if strip_v_prefix and tag.startswith("v"):
        return tag[1:]
    return tag


def extract_match(value: str, pattern: re.Pattern) -> str:
    """Extract a substring via ``pattern``.

    Uses capture group 1 when the pattern has groups, otherwise the whole
    match. Returns ``""`` when ``value`` is empty or nothing matches.
    """
    if not value:
        return ""
    match = pattern.search(value)
    if not match:
        return ""
    if match.groups():
        return match.group(1)
    return match.group(0)


def resolve_version(
    cfg: AltgenConfig, tag_version: str, source_value: str
) -> str:
    """App version for one release asset.

    With ``version_pattern`` configured, extract the version from the
    release ``name`` (default) or the asset filename (``version_source =
    "filename"``); fall back to the tag-derived version when the pattern
    does not match or is unset.
    """
    if cfg.versions.version_pattern is None:
        return tag_version
    extracted = extract_match(source_value or "", cfg.version_re)
    if extracted:
        return extracted
    return tag_version


def build_version_entry(
    cfg: AltgenConfig, release: dict, asset: dict, version: str
) -> dict:
    """One AltStore version entry for one release asset."""
    download_url = asset.get("browser_download_url", "")
    release_body = (release.get("body") or "").strip() or cfg.app.description or ""
    build_version = extract_match(asset.get("name") or "", cfg.build_re)

    entry: dict = {"version": version}
    if build_version:
        entry["buildVersion"] = build_version
    entry["date"] = short_date(release.get("published_at", ""))
    entry["localizedDescription"] = release_body
    entry["downloadURL"] = download_url
    entry["size"] = asset.get("size", 0)
    if cfg.app.min_os_version is not None:
        entry["minOSVersion"] = cfg.app.min_os_version
    return entry


def build_news_entry(
    cfg: AltgenConfig, release: dict, version: str, tag: str
) -> dict:
    """One AltStore news entry for one release.

    Key order follows the AltStore news spec. ``appID`` is the app's
    ``bundle_identifier``. The date is a full ISO timestamp, and the
    identifier is derived from the release tag (``release-<tag>``). Title
    and caption templates may use ``{name}``, ``{version}``, ``{tag}``,
    and ``{date}`` (humanized, e.g. 07 Aug 2026) placeholders.
    """
    published = release.get("published_at", "")
    fmt = {
        "name": cfg.app.name,
        "version": version,
        "tag": tag,
        "date": human_date(published),
    }
    title = cfg.news.title_template.format(**fmt)
    caption = cfg.news.caption_template.format(**fmt)
    entry: dict = {
        "appID": cfg.app.bundle_identifier,
        "title": title,
        "identifier": f"release-{tag}",
        "caption": caption,
        "date": iso_datetime(published),
    }
    if cfg.app.tint_color is not None:
        entry["tintColor"] = cfg.app.tint_color
    if cfg.news.image_url is not None:
        entry["imageURL"] = cfg.news.image_url
    entry["notify"] = True
    entry["url"] = f"https://github.com/{cfg.github.repo}/releases/tag/{tag}"
    return entry


def build_source(
    cfg: AltgenConfig,
    releases: list[dict],
    log: Callable[[str], None] | None = None,
) -> dict:
    """Build a complete AltStore source document from config + releases.

    ``log``, when given, receives a human-readable reason for each release
    that is skipped (used by ``--verbose``).
    """
    data: dict = {
        "name": cfg.source.name,
        "subtitle": cfg.source.subtitle,
        "description": cfg.source.description,
    }
    if cfg.source.icon_url is not None:
        data["iconURL"] = cfg.source.icon_url
    if cfg.source.website is not None:
        data["website"] = cfg.source.website
    if cfg.source.tint_color is not None:
        data["tintColor"] = cfg.source.tint_color
    data["apps"] = []

    app_entry: dict = {
        "name": cfg.app.name,
        "bundleIdentifier": cfg.app.bundle_identifier,
        "developerName": cfg.app.developer_name,
        "subtitle": cfg.app.subtitle,
        "localizedDescription": cfg.app.description,
    }
    if cfg.app.icon_url is not None:
        app_entry["iconURL"] = cfg.app.icon_url
    if cfg.app.screenshots:
        app_entry["screenshots"] = list(cfg.app.screenshots)
    if cfg.app.tint_color is not None:
        app_entry["tintColor"] = cfg.app.tint_color
    app_entry["versions"] = []
    data["apps"].append(app_entry)

    def log_skip(reason: str) -> None:
        if log is not None:
            log(reason)

    news: list[dict] = []
    news_versions: list[list[str]] = []
    for release in releases:
        tag = release.get("tag_name") or ""
        if release.get("draft"):
            log_skip(f"skip {tag or '<no tag>'}: draft")
            continue
        if release.get("prerelease") and not cfg.versions.include_prereleases:
            log_skip(f"skip {tag}: prerelease")
            continue

        tag_version = version_from_tag(tag, cfg.versions.strip_v_prefix)
        if not tag_version:
            log_skip(f"skip {tag or '<no tag>'}: empty version")
            continue

        assets = release.get("assets") or []
        ipa_assets = [
            a
            for a in assets
            if cfg.asset_re.search((a.get("name") or "").lower())
        ]
        if not ipa_assets:
            log_skip(f"skip {tag}: no matching assets")
            continue

        # Version comes from the release name (default) or the asset
        # filename (version_source = "filename"), falling back to the tag.
        release_versions: list[str] = []
        for asset in ipa_assets:
            source_value = (
                (release.get("name") or "")
                if cfg.versions.version_source == "release"
                else (asset.get("name") or "")
            )
            version = resolve_version(cfg, tag_version, source_value)
            release_versions.append(version)
            app_entry["versions"].append(
                build_version_entry(cfg, release, asset, version)
            )

        if cfg.news.enabled:
            news.append(
                build_news_entry(cfg, release, release_versions[0], tag)
            )
            # Track every asset version so the cap filter below can match
            # this release's news when any of its versions is kept.
            news_versions.append(release_versions)

    app_entry["versions"] = sorted(
        app_entry["versions"],
        key=lambda v: (v.get("date", ""), v.get("version", "")),
        reverse=True,
    )
    if cfg.versions.max_versions is not None:
        app_entry["versions"] = app_entry["versions"][: cfg.versions.max_versions]
        # News follows the same convention as versions: one entry per
        # release, so drop news for releases whose versions were all
        # capped away.
        kept = {v["version"] for v in app_entry["versions"]}
        news = [
            n for n, vs in zip(news, news_versions) if any(v in kept for v in vs)
        ]

    news.sort(key=lambda n: n.get("date", ""), reverse=True)
    if cfg.news.max_entries is not None:
        news = news[: cfg.news.max_entries]
    data["news"] = news

    return data


def serialize(data: dict) -> str:
    """Render the source document as the final apps.json text."""
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
