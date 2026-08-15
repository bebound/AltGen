"""Configuration loading and validation for altgen.

One TOML config describes one app; see README.md for the full schema.
snake_case TOML keys are mapped to AltStore's camelCase JSON keys.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib


class ConfigError(Exception):
    """Invalid altgen configuration; the message names the offending TOML key."""


_TINT_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")

DEFAULT_ASSET_PATTERN = r"\.ipa$"
DEFAULT_BUILD_VERSION_PATTERN = r"\+(\d+)\.ipa$"
DEFAULT_NEWS_TITLE_TEMPLATE = "{name} {version} - {date}"
DEFAULT_NEWS_CAPTION_TEMPLATE = "{name} {version} is available."
NEWS_TEMPLATE_KEYS = ("name", "version", "tag", "date")


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GitHubConfig:
    repo: str
    token: str | None = None


@dataclass(frozen=True)
class SourceConfig:
    name: str
    subtitle: str = ""
    description: str = ""
    icon_url: str | None = None
    website: str | None = None
    tint_color: str | None = None


@dataclass(frozen=True)
class AppConfig:
    name: str
    bundle_identifier: str
    developer_name: str = ""
    subtitle: str = ""
    description: str = ""
    icon_url: str | None = None
    screenshots: tuple[str, ...] = ()
    tint_color: str | None = None
    min_os_version: str | None = None


@dataclass(frozen=True)
class VersionsConfig:
    strip_v_prefix: bool = True
    include_prereleases: bool = False
    asset_pattern: str = DEFAULT_ASSET_PATTERN
    build_version_pattern: str = DEFAULT_BUILD_VERSION_PATTERN
    max_versions: int | None = 1  # default: latest version only; None = all


@dataclass(frozen=True)
class NewsConfig:
    enabled: bool = True
    title_template: str = DEFAULT_NEWS_TITLE_TEMPLATE
    caption_template: str = DEFAULT_NEWS_CAPTION_TEMPLATE
    image_url: str | None = None  # omitted from JSON when unset
    max_entries: int | None = None  # None = unlimited


@dataclass(frozen=True)
class OutputConfig:
    path: Path = Path("apps.json")


@dataclass(frozen=True)
class AltgenConfig:
    github: GitHubConfig
    source: SourceConfig
    app: AppConfig
    versions: VersionsConfig
    news: NewsConfig
    output: OutputConfig
    config_dir: Path
    asset_re: re.Pattern = field(init=False)  # matches IPA asset names (IGNORECASE)
    build_re: re.Pattern = field(init=False)  # extracts buildVersion from filename

    def __post_init__(self) -> None:
        # Validates regardless of how the config was built (TOML or CLI),
        # so CLI overrides can never smuggle in bad values.
        if not _REPO_RE.match(self.github.repo):
            raise ConfigError(
                f"github repo must be 'owner/name', got {self.github.repo!r}"
            )
        for section, tint in (
            ("source", self.source.tint_color),
            ("app", self.app.tint_color),
        ):
            if tint is not None and not _TINT_RE.match(tint):
                raise ConfigError(f"[{section}] tint_color must be #RRGGBB, got {tint!r}")
        try:
            asset_re = re.compile(self.versions.asset_pattern, re.IGNORECASE)
            build_re = re.compile(self.versions.build_version_pattern)
        except re.error as exc:
            raise ConfigError(f"invalid regex: {exc}") from exc
        object.__setattr__(self, "asset_re", asset_re)
        object.__setattr__(self, "build_re", build_re)


# ---------------------------------------------------------------------------
# TOML table schemas
# ---------------------------------------------------------------------------

_TABLES: dict[str, set[str]] = {
    "github": {"repo", "token"},
    "source": {"name", "subtitle", "description", "icon_url", "website", "tint_color"},
    "app": {
        "name",
        "bundle_identifier",
        "developer_name",
        "subtitle",
        "description",
        "icon_url",
        "screenshots",
        "tint_color",
        "min_os_version",
    },
    "versions": {
        "strip_v_prefix",
        "include_prereleases",
        "asset_pattern",
        "build_version_pattern",
        "max_versions",
    },
    "news": {
        "enabled",
        "title_template",
        "caption_template",
        "image_url",
        "max_entries",
    },
    "output": {"path"},
}


def _table(raw: dict, name: str) -> dict:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] must be a table, got {type(value).__name__}")
    return value


def _check_keys(table: dict, name: str) -> None:
    for key in table:
        if key not in _TABLES[name]:
            allowed = ", ".join(sorted(_TABLES[name]))
            raise ConfigError(f"[{name}] unknown key {key!r}; allowed: {allowed}")


def _get_str(table: dict, key: str, section: str, *, required: bool = False) -> str | None:
    if key not in table or table[key] is None:
        if required:
            raise ConfigError(f"[{section}] {key} is required")
        return None
    value = table[key]
    if not isinstance(value, str):
        raise ConfigError(
            f"[{section}] {key} must be a string, got {type(value).__name__}"
        )
    return value


def _get_bool(table: dict, key: str, section: str, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(
            f"[{section}] {key} must be a boolean, got {type(value).__name__}"
        )
    return value


def _get_cap(
    table: dict, key: str, section: str, *, default: int | None
) -> int | None:
    """Optional non-negative int cap; 0 means unlimited, absent/None falls
    back to ``default``."""
    if key not in table or table[key] is None:
        return default
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            f"[{section}] {key} must be an integer, got {type(value).__name__}"
        )
    if value < 0:
        raise ConfigError(f"[{section}] {key} must be >= 0, got {value}")
    if value == 0:
        return None
    return value


def _get_screenshots(table: dict, section: str) -> tuple[str, ...]:
    if "screenshots" not in table:
        return ()
    value = table["screenshots"]
    if not isinstance(value, list) or not all(isinstance(s, str) for s in value):
        raise ConfigError(f"[{section}] screenshots must be a list of strings")
    return tuple(value)


def _get_template(
    table: dict, key: str, section: str, default: str | None
) -> str | None:
    """String template using NEWS_TEMPLATE_KEYS placeholders, or ``default``
    when absent. Validated by formatting with dummy values, so a bad
    placeholder is a config error instead of a runtime crash."""
    value = _get_str(table, key, section)
    if value is None:
        return default
    try:
        value.format(**{k: "" for k in NEWS_TEMPLATE_KEYS})
    except (KeyError, IndexError, ValueError) as exc:
        raise ConfigError(
            f"[{section}] {key} has an invalid placeholder: {exc}"
        ) from None
    return value


def _get_tint(table: dict, key: str, section: str) -> str | None:
    value = _get_str(table, key, section)
    if value is None:
        return None
    if not _TINT_RE.match(value):
        raise ConfigError(f"[{section}] {key} must be #RRGGBB, got {value!r}")
    return value


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_config(path: Path) -> AltgenConfig:
    """Load and validate a TOML config file.

    Relative ``[output] path`` values are resolved against the config file's
    directory.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc

    for key in raw:
        if key not in _TABLES:
            allowed = ", ".join(sorted(_TABLES))
            raise ConfigError(f"unknown table [{key}]; allowed: {allowed}")

    config_dir = Path(path).resolve().parent

    gh_table = _table(raw, "github")
    _check_keys(gh_table, "github")
    repo = _get_str(gh_table, "repo", "github", required=True) or ""
    if not _REPO_RE.match(repo):
        raise ConfigError(
            f"[github] repo must be 'owner/name', got {repo!r}"
        )

    src_table = _table(raw, "source")
    _check_keys(src_table, "source")
    source = SourceConfig(
        name=_get_str(src_table, "name", "source") or repo.split("/", 1)[-1],
        subtitle=_get_str(src_table, "subtitle", "source") or "",
        description=_get_str(src_table, "description", "source") or "",
        icon_url=_get_str(src_table, "icon_url", "source") or None,
        website=_get_str(src_table, "website", "source") or None,
        tint_color=_get_tint(src_table, "tint_color", "source"),
    )

    app_table = _table(raw, "app")
    _check_keys(app_table, "app")
    app = AppConfig(
        name=_get_str(app_table, "name", "app", required=True) or "",
        bundle_identifier=_get_str(
            app_table, "bundle_identifier", "app", required=True
        )
        or "",
        developer_name=_get_str(app_table, "developer_name", "app") or "",
        subtitle=_get_str(app_table, "subtitle", "app") or "",
        description=_get_str(app_table, "description", "app") or "",
        icon_url=_get_str(app_table, "icon_url", "app") or None,
        screenshots=_get_screenshots(app_table, "app"),
        tint_color=_get_tint(app_table, "tint_color", "app"),
        min_os_version=_get_str(app_table, "min_os_version", "app") or None,
    )
    # [app] falls back to [source] for icon and tint color when unset.
    if app.icon_url is None:
        app = replace(app, icon_url=source.icon_url)
    if app.tint_color is None:
        app = replace(app, tint_color=source.tint_color)

    ver_table = _table(raw, "versions")
    _check_keys(ver_table, "versions")
    versions = VersionsConfig(
        strip_v_prefix=_get_bool(ver_table, "strip_v_prefix", "versions", True),
        include_prereleases=_get_bool(
            ver_table, "include_prereleases", "versions", False
        ),
        asset_pattern=_get_str(ver_table, "asset_pattern", "versions")
        or DEFAULT_ASSET_PATTERN,
        build_version_pattern=_get_str(
            ver_table, "build_version_pattern", "versions"
        )
        or DEFAULT_BUILD_VERSION_PATTERN,
        max_versions=_get_cap(
            ver_table, "max_versions", "versions", default=1
        ),
    )

    news_table = _table(raw, "news")
    _check_keys(news_table, "news")
    news = NewsConfig(
        enabled=_get_bool(news_table, "enabled", "news", True),
        title_template=_get_template(
            news_table, "title_template", "news", DEFAULT_NEWS_TITLE_TEMPLATE
        ),
        caption_template=_get_template(
            news_table, "caption_template", "news", DEFAULT_NEWS_CAPTION_TEMPLATE
        ),
        image_url=_get_str(news_table, "image_url", "news") or None,
        max_entries=_get_cap(
            news_table, "max_entries", "news", default=None
        ),
    )

    out_table = _table(raw, "output")
    _check_keys(out_table, "output")
    out_path = Path(_get_str(out_table, "path", "output") or "apps.json")
    if not out_path.is_absolute():
        out_path = config_dir / out_path
    output = OutputConfig(path=out_path)

    return AltgenConfig(
        github=GitHubConfig(repo=repo, token=_get_str(gh_table, "token", "github") or None),
        source=source,
        app=app,
        versions=versions,
        news=news,
        output=output,
        config_dir=config_dir,
    )


def default_config(
    repo: str,
    app_name: str,
    bundle_identifier: str,
    *,
    token: str | None = None,
    config_dir: Path = Path.cwd(),
) -> AltgenConfig:
    """Build a config from CLI arguments alone (no TOML file)."""
    name = repo.split("/", 1)[-1]
    source = SourceConfig(
        name=name,
        subtitle=f"Auto-updated AltStore source for {name}",
        description=f"AltStore source for {name}",
    )
    app = AppConfig(
        name=app_name,
        bundle_identifier=bundle_identifier,
        developer_name=repo.split("/", 1)[0],
        subtitle=f"Latest {app_name} release",
        description=f"{app_name} iOS app builds from GitHub releases",
    )
    return AltgenConfig(
        github=GitHubConfig(repo=repo, token=token),
        source=source,
        app=app,
        versions=VersionsConfig(),
        news=NewsConfig(),
        output=OutputConfig(path=config_dir / "apps.json"),
        config_dir=config_dir,
    )


# ---------------------------------------------------------------------------
# CLI override merge
# ---------------------------------------------------------------------------

def apply_cli_overrides(config: AltgenConfig, args) -> AltgenConfig:
    """Replace config fields whose CLI flag was explicitly provided.

    ``args`` is an ``argparse.Namespace`` where every override flag defaults
    to ``None``, so absent flags never clobber TOML values. ``-o/--output``
    resolves against the current working directory (TOML ``[output] path``
    resolves against the config file's directory).
    """
    github = config.github
    source = config.source
    app = config.app
    versions = config.versions
    output = config.output

    def get(name):
        return getattr(args, name, None)

    if get("repo") is not None:
        github = replace(github, repo=args.repo)
    if get("token") is not None:
        github = replace(github, token=args.token)
    if get("name") is not None:
        source = replace(source, name=args.name)
    if get("subtitle") is not None:
        source = replace(source, subtitle=args.subtitle)
    if get("description") is not None:
        source = replace(source, description=args.description)
    if get("icon_url") is not None:
        source = replace(source, icon_url=args.icon_url)
    if get("website") is not None:
        source = replace(source, website=args.website)
    if get("tint_color") is not None:
        source = replace(source, tint_color=args.tint_color)
    if get("app_name") is not None:
        app = replace(app, name=args.app_name)
    if get("bundle_id") is not None:
        app = replace(app, bundle_identifier=args.bundle_id)
    if get("developer_name") is not None:
        app = replace(app, developer_name=args.developer_name)
    if get("app_subtitle") is not None:
        app = replace(app, subtitle=args.app_subtitle)
    if get("app_description") is not None:
        app = replace(app, description=args.app_description)
    if get("app_icon_url") is not None:
        app = replace(app, icon_url=args.app_icon_url)
    if get("app_tint_color") is not None:
        app = replace(app, tint_color=args.app_tint_color)
    if get("min_os_version") is not None:
        app = replace(app, min_os_version=args.min_os_version)
    if get("screenshots") is not None:
        app = replace(app, screenshots=tuple(args.screenshots))
    if get("include_prereleases") is not None:
        versions = replace(versions, include_prereleases=args.include_prereleases)
    if get("max_versions") is not None:
        versions = replace(versions, max_versions=args.max_versions or None)
    if get("output") is not None:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = (Path.cwd() / out_path).resolve()
        output = replace(output, path=out_path)

    return replace(
        config,
        github=github,
        source=source,
        app=app,
        versions=versions,
        output=output,
    )
