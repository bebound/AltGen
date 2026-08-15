"""Merge multiple apps.json documents into a single AltStore source.

``apps`` and ``news`` are extracted from the input files in their given
order; root-level metadata comes from the merge config or CLI. Duplicate
app bundle identifiers and duplicate news identifiers are rejected, since
a valid AltStore source must not contain them.
"""

from __future__ import annotations

from altgen.config import SourceConfig


class MergeError(Exception):
    """Invalid apps.json input; the message names the offending file."""


def merge_sources(inputs: list[tuple[str, dict]], source: SourceConfig) -> dict:
    """Merge ``inputs`` (``(path, parsed JSON)`` pairs) into one source
    document.

    App entries keep their input order; news entries from each input (root
    ``news`` plus each app's ``news``) are combined and sorted newest-first
    by ``date``.
    """
    apps: list[dict] = []
    news: list[dict] = []
    seen_app_ids: dict[str, str] = {}
    seen_news_ids: dict[str, str] = {}

    def add_news(entry, path: str) -> None:
        identifier = entry.get("identifier") if isinstance(entry, dict) else None
        if not isinstance(identifier, str) or not identifier:
            raise MergeError(f"{path}: news entry without identifier")
        if identifier in seen_news_ids:
            raise MergeError(
                f"duplicate news identifier {identifier} in "
                f"{seen_news_ids[identifier]} and {path}"
            )
        seen_news_ids[identifier] = path
        news.append(entry)

    for path, doc in inputs:
        if not isinstance(doc, dict):
            raise MergeError(f"{path}: not a JSON object")
        doc_apps = doc.get("apps")
        if not isinstance(doc_apps, list):
            raise MergeError(f"{path}: not a valid apps.json (missing 'apps' list)")
        for app in doc_apps:
            if not isinstance(app, dict):
                raise MergeError(f"{path}: app entry is not an object")
            bundle_id = app.get("bundleIdentifier")
            if not isinstance(bundle_id, str) or not bundle_id:
                raise MergeError(f"{path}: app without bundleIdentifier")
            if bundle_id in seen_app_ids:
                raise MergeError(
                    f"duplicate bundleIdentifier {bundle_id} in "
                    f"{seen_app_ids[bundle_id]} and {path}"
                )
            seen_app_ids[bundle_id] = path
            apps.append(app)
            app_news = app.get("news")
            if app_news is not None and not isinstance(app_news, list):
                raise MergeError(f"{path}: app 'news' must be a list")
            for entry in app_news or []:
                add_news(entry, path)
        doc_news = doc.get("news")
        if doc_news is not None and not isinstance(doc_news, list):
            raise MergeError(f"{path}: 'news' must be a list")
        for entry in doc_news or []:
            add_news(entry, path)

    news.sort(key=lambda n: n.get("date", ""), reverse=True)

    data: dict = {
        "name": source.name,
        "subtitle": source.subtitle,
        "description": source.description,
    }
    if source.icon_url is not None:
        data["iconURL"] = source.icon_url
    if source.website is not None:
        data["website"] = source.website
    if source.tint_color is not None:
        data["tintColor"] = source.tint_color
    data["apps"] = apps
    data["news"] = news
    return data
