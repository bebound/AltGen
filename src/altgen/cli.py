"""Command-line interface for altgen.

Two modes: build a source from GitHub Releases (default), or merge
existing apps.json files (``altgen merge``).

Exit codes: 0 success (including an empty source), 1 GitHub/IO error,
2 usage or configuration error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from altgen import __version__
from altgen.config import (
    _TINT_RE,
    ConfigError,
    OutputConfig,
    SourceConfig,
    apply_cli_overrides,
    default_config,
    load_config,
    load_merge_config,
)
from altgen.github import GithubError, fetch_releases
from altgen.merge import MergeError, merge_sources
from altgen.source import build_source, serialize

USAGE_ERROR = 2
RUNTIME_ERROR = 1
OK = 0


def _add_common_flags(parser) -> None:
    """Flags shared by the build and merge modes: config, root source
    values, output path, and quiet. Dest names must match between the two
    parsers so a single Namespace serves both."""
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="TOML config file (one app per config)",
    )
    parser.add_argument("--name", help="source name")
    parser.add_argument("--subtitle", help="source subtitle")
    parser.add_argument("--description", help="source description")
    parser.add_argument("--icon-url", help="source icon URL")
    parser.add_argument("--website", help="source website URL")
    parser.add_argument("--tint-color", metavar="#RRGGBB", help="source tint color")
    parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="write apps.json to PATH (relative paths resolve against the cwd)",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="suppress the success message"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="altgen",
        description=(
            "Generate an AltStore apps.json source from GitHub Releases "
            "IPA assets, or merge existing apps.json files."
        ),
    )
    _add_common_flags(parser)
    parser.add_argument(
        "--repo",
        metavar="OWNER/REPO",
        help="GitHub repository to read releases from (required without -c)",
    )
    parser.add_argument(
        "--token",
        metavar="TOKEN",
        help=(
            "GitHub API token (overrides GITHUB_TOKEN env and "
            "[github] token)"
        ),
    )
    parser.add_argument(
        "--app-name", help="app name (required without -c)"
    )
    parser.add_argument(
        "--bundle-id", help="app bundle identifier (required without -c)"
    )
    parser.add_argument("--developer-name", help="app developer name")
    parser.add_argument("--app-subtitle", help="app subtitle")
    parser.add_argument(
        "--app-description",
        help="app description (fallback when a release body is empty)",
    )
    parser.add_argument("--app-icon-url", help="app icon URL")
    parser.add_argument("--app-tint-color", metavar="#RRGGBB", help="app tint color")
    parser.add_argument("--min-os-version", help="minimum iOS version per release")
    parser.add_argument(
        "--screenshots",
        nargs="+",
        metavar="URL",
        help="app screenshot URLs (replaces the configured list)",
    )
    parser.add_argument(
        "--include-prereleases",
        action="store_true",
        default=None,
        help="include prereleases (default: skip them)",
    )
    parser.add_argument(
        "--max-versions",
        type=int,
        metavar="N",
        help="keep only the newest N versions (default: 1; 0 = all versions)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="log skipped releases to stderr (repeat for more detail)",
    )
    parser.add_argument(
        "--version", action="version", version=f"altgen {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    merge = subparsers.add_parser(
        "merge",
        help="merge multiple apps.json files into one source",
        description=(
            "Combine apps and news from several apps.json files into one "
            "source; root values come from -c config or the flags below."
        ),
    )
    merge.add_argument(
        "files",
        nargs="+",
        metavar="APPS_JSON",
        help="apps.json files to merge",
    )
    _add_common_flags(merge)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if getattr(args, "command", None) == "merge":
            return _run_merge(parser, args)
        if args.config is None and not (args.repo and args.app_name and args.bundle_id):
            parser.error(
                "either -c/--config or --repo + --app-name + --bundle-id "
                "is required"
            )
    except SystemExit as exc:
        return int(exc.code)

    try:
        if args.config is not None:
            config = load_config(Path(args.config))
        else:
            config = default_config(args.repo, args.app_name, args.bundle_id)
        config = apply_cli_overrides(config, args)
    except ConfigError as exc:
        print(f"altgen: {exc}", file=sys.stderr)
        return USAGE_ERROR

    # Token precedence: --token > GITHUB_TOKEN env > [github].token.
    token = (
        args.token
        if args.token is not None
        else os.environ.get("GITHUB_TOKEN") or config.github.token
    )

    if args.verbose:
        print(f"fetching releases for {config.github.repo}…", file=sys.stderr)

    try:
        releases = fetch_releases(config.github.repo, token)
    except GithubError as exc:
        print(f"altgen: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    data = build_source(
        config,
        releases,
        log=(lambda msg: print(msg, file=sys.stderr)) if args.verbose else None,
    )
    text = serialize(data)

    try:
        config.output.path.parent.mkdir(parents=True, exist_ok=True)
        config.output.path.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(f"altgen: cannot write {config.output.path}: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    n_versions = len(data["apps"][0]["versions"])
    n_news = len(data["news"])
    if not n_versions:
        print(
            f"warning: no matching releases found for {config.github.repo}",
            file=sys.stderr,
        )
    if not args.quiet:
        print(
            f"Wrote {config.output.path} ({n_versions} versions, {n_news} news)"
        )
    return OK


def _run_merge(parser: argparse.ArgumentParser, args) -> int:
    """Merge mode: combine apps.json inputs into one source document."""
    if args.config is not None:
        try:
            merge_config = load_merge_config(Path(args.config))
        except ConfigError as exc:
            print(f"altgen: {exc}", file=sys.stderr)
            return USAGE_ERROR
        source, output = merge_config.source, merge_config.output
    else:
        source = SourceConfig(name="", subtitle="", description="")
        output = OutputConfig(path=Path.cwd() / "apps.json")

    if args.tint_color is not None and not _TINT_RE.match(args.tint_color):
        parser.error("--tint-color must be #RRGGBB")
    # CLI flags override TOML values.
    if args.name is not None:
        source = replace(source, name=args.name)
    if args.subtitle is not None:
        source = replace(source, subtitle=args.subtitle)
    if args.description is not None:
        source = replace(source, description=args.description)
    if args.icon_url is not None:
        source = replace(source, icon_url=args.icon_url)
    if args.website is not None:
        source = replace(source, website=args.website)
    if args.tint_color is not None:
        source = replace(source, tint_color=args.tint_color)
    if not source.name:
        parser.error("--name (or [source] name in the config) is required for merge")
    if args.output is not None:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = (Path.cwd() / out_path).resolve()
        output = replace(output, path=out_path)

    inputs: list[tuple[str, dict]] = []
    for path_str in args.files:
        path = Path(path_str)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"altgen: cannot read {path}: {exc}", file=sys.stderr)
            return RUNTIME_ERROR
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            print(f"altgen: {path}: invalid JSON: {exc}", file=sys.stderr)
            return USAGE_ERROR
        inputs.append((str(path), doc))

    try:
        data = merge_sources(inputs, source)
    except MergeError as exc:
        print(f"altgen: {exc}", file=sys.stderr)
        return USAGE_ERROR

    text = serialize(data)
    try:
        output.path.parent.mkdir(parents=True, exist_ok=True)
        output.path.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(f"altgen: cannot write {output.path}: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    if not args.quiet:
        print(
            f"Wrote {output.path} ({len(data['apps'])} apps, "
            f"{len(data['news'])} news)"
        )
    return OK
