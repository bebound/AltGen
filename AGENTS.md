# AGENTS.md

Guidance for AI coding agents working in this repository. User-facing
documentation lives in README.md.

## What this is

altgen is a Python CLI that generates
[AltStore](https://faq.altstore.io/developers/make-a-source) `apps.json`
source documents from GitHub Releases IPA assets, and can merge several
existing `apps.json` files into one source (`altgen merge`).

## Commands

```sh
uv run pytest      # run the test suite (fully offline)
uv build           # build sdist + wheel
```

Requires Python >= 3.10. The virtualenv is `.venv/`.

## Layout

- `src/altgen/__init__.py` — `__version__` is the single source of truth.
  `pyproject.toml` reads it via `[tool.setuptools.dynamic] version =
  {attr = "altgen.__version__"}`. Bump versions only here.
- `src/altgen/config.py` — TOML config dataclasses and validation:
  `load_config` (build mode), `load_merge_config` (merge mode, only
  `[source]` + `[output]` tables), `apply_cli_overrides` (CLI flag > TOML).
- `src/altgen/source.py` — pure functions building the source document
  from a config + release dicts. No network, no IO.
- `src/altgen/github.py` — GitHub Releases API client (`fetch_releases`);
  the only network caller, patched in tests.
- `src/altgen/merge.py` — merges parsed apps.json documents
  (`merge_sources`); rejects duplicate bundle identifiers and news
  identifiers.
- `src/altgen/cli.py` — argparse entry point. Default mode builds from
  GitHub; the `merge` subcommand combines apps.json files. Exit codes:
  `0` success, `1` runtime (GitHub API / IO / write), `2` usage/config.
- `tests/` — pytest, fully offline. `tests/fixtures/` holds captured
  GitHub API responses.
- `examples/piliplus.toml` — reference config. `tests/test_equivalence.py`
  asserts its output byte-for-byte against
  `tests/fixtures/piliplus_expected.json`.

## Design rules — do not break

1. **Deterministic, spec-ordered JSON.** Key order follows the AltStore
   spec and is stable, so output is byte-for-byte reproducible. Add keys
   in spec order:
   - source root: `name, subtitle, description, iconURL, website,
     tintColor, apps, news`
   - app: `name, bundleIdentifier, developerName, subtitle,
     localizedDescription, iconURL, screenshots, tintColor, versions,
     news`
   - version entry: `version, buildVersion, date, localizedDescription,
     downloadURL, size, minOSVersion`
   - news entry: `appID, title, identifier, caption, date, tintColor,
     imageURL, notify, url`
2. **snake_case TOML → camelCase JSON.** TOML keys are snake_case
   (`bundle_identifier`, `min_os_version`); JSON keys are camelCase
   (`bundleIdentifier`, `minOSVersion`). Unknown config keys and tables
   are rejected with errors, never silently ignored.
3. **Optional values are omitted.** A `None` config field produces no
   JSON key (e.g. `iconURL`, `tintColor`, `imageURL` are absent when
   unset).
4. **Pure pipeline.** `build_source(config, releases)` and
   `merge_sources(inputs, source)` are pure functions; tests exercise
   them directly with fixture data.
5. **Version semantics.**
   - `max_versions` defaults to `1` (newest version only); `0` means all
     versions; the internal "unlimited" sentinel is `None` (see
     `_get_cap`).
   - News follows `max_versions`: one news entry per kept version, so
     versions dropped by the cap contribute no news. `news.max_entries`
     caps further.
   - News `identifier` = `release-<tag>` (raw release tag, not the
     v-stripped version); news `date` is a full ISO timestamp, while
     version-entry dates are `YYYY-MM-DD` (short date).
   - News `appID` always comes from `[app] bundle_identifier`; it is not
     separately configurable.
   - `title_template` / `caption_template` support `{name}`, `{version}`,
     `{tag}`, `{date}` (humanized, e.g. `07 Aug 2026`); templates are
     validated at config load, so bad placeholders are config errors.
6. **CLI flag > TOML.** `apply_cli_overrides` replaces only fields whose
   flag was explicitly provided (flags default to `None`). `-o` resolves
   against the cwd; `[output] path` resolves against the config file's
   directory. The build and merge modes share flag dests via
   `_add_common_flags` in `cli.py`.
7. **Strict input validation in merge.** Every input app must have a
   non-empty `bundleIdentifier`, every news entry a non-empty
   `identifier`; duplicates across inputs raise `MergeError` (exit 2).

## When changing behavior

- If a change affects the example output (key order, news format, caps,
  config semantics), regenerate the equivalence fixture by running the
  real pipeline over `tests/fixtures/piliplus_releases.json` with
  `examples/piliplus.toml`, and update the `test_equivalence.py`
  docstring if the expected semantics changed.
- After any code change, keep the examples in sync: update the example
  configs (`examples/piliplus.toml`, `examples/merge.toml`) when config
  surface or defaults change, and regenerate their JSON outputs:
  - `examples/apps.json` — regenerate offline with the fixture-based
    pipeline (same approach as the equivalence fixture), or live with
    `uv run altgen -c examples/piliplus.toml`.
  - `examples/all-apps.json` — regenerate with
    `uv run altgen merge -c examples/merge.toml examples/apps.json`.
- Update README.md and example config comments when config surface or
  defaults change.
- Keep tests offline — never call the GitHub API in tests.
- Match existing style: module docstrings, typed signatures,
  `from __future__ import annotations`.
