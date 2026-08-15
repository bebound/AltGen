"""Command-line interface for altgen.

Exit codes: 0 success (including an empty source), 1 GitHub/IO error,
2 usage or configuration error.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from altgen import __version__
from altgen.config import (
    ConfigError,
    apply_cli_overrides,
    default_config,
    load_config,
)
from altgen.github import GithubError, fetch_releases
from altgen.source import build_source, serialize

USAGE_ERROR = 2
RUNTIME_ERROR = 1
OK = 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="altgen",
        description=(
            "Generate an AltStore apps.json source from GitHub Releases "
            "IPA assets."
        ),
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="TOML config file (one app per config)",
    )
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
    parser.add_argument("--name", help="source name")
    parser.add_argument("--subtitle", help="source subtitle")
    parser.add_argument("--description", help="source description")
    parser.add_argument("--icon-url", help="source icon URL")
    parser.add_argument("--website", help="source website URL")
    parser.add_argument("--tint-color", metavar="#RRGGBB", help="source tint color")
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
        "-o",
        "--output",
        metavar="PATH",
        help="write apps.json to PATH (relative paths resolve against the cwd)",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="suppress the success message"
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
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
