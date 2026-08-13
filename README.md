# altgen

Generate [AltStore](https://faq.altstore.io/developers/make-a-source)
`apps.json` source files from GitHub Releases IPA assets.

Static app metadata (name, bundle identifier, icon and screenshot URLs,
descriptions…) comes from a TOML config; everything dynamic (version,
build version, release date, download URL, file size, release notes) is
read live from the GitHub Releases API.

```
GitHub Releases API ──┐
                      ├──► altgen ──► apps.json
app config TOML ──────┘
```

## Install

```sh
pip install .          # or: pip install git+https://github.com/…
altgen --version
```

Requires Python ≥ 3.10.

## Usage

One TOML config = one app = one `apps.json`:

```sh
altgen -c piliplus.toml          # writes apps.json next to the config
altgen -c piliplus.toml -o out/piliplus.json   # override output path
```

Or skip the config file entirely for a quick single-app source
(any CLI flag overrides its TOML counterpart):

```sh
altgen --repo owner/App --app-name App --bundle-id com.owner.app -o apps.json
```

Hosting many sources is just many configs — loop over them or use a CI
matrix, one `altgen -c <config>` per app.

### GitHub token

Unauthenticated requests are limited to 60/hour; a token raises that to
5,000/hour. Precedence: `--token` > `GITHUB_TOKEN` env var > `[github] token`.

## TOML schema

Only `[github] repo`, `[app] name`, and `[app] bundle_identifier` are
required. Keys are snake_case in TOML and become the AltStore camelCase
JSON keys (`bundle_identifier` → `bundleIdentifier`, `icon_url` →
`iconURL`, `min_os_version` → `minOSVersion`, …). Unknown keys are
rejected with an error.

See [examples/piliplus.toml](examples/piliplus.toml) for a full example.

```toml
[github]
repo = "owner/App"               # REQUIRED: GitHub repo with releases
token = ""                       # optional (see above)

[source]                         # the source this apps.json describes
name = "App"                     # defaults to the repo name
subtitle = ""
description = ""
icon_url = ""                    # omitted from JSON when unset
website = ""
tint_color = "#00AEEF"           # must be #RRGGBB

[app]                            # the app inside the source
name = "App"                     # REQUIRED
bundle_identifier = "com.x.y"    # REQUIRED
developer_name = ""              # defaults to the repo owner (CLI mode)
subtitle = ""
description = ""                 # fallback when a release body is empty
icon_url = ""                    # falls back to [source].icon_url
screenshots = ["https://…"]
tint_color = ""                  # falls back to [source].tint_color
min_os_version = "14.0"          # omitted from versions when unset

[versions]
strip_v_prefix = true            # tag "v1.2.3" → version "1.2.3"
include_prereleases = false      # drafts are always skipped
asset_pattern = "\\.ipa$"        # regex, case-insensitive search on asset name
build_version_pattern = "\\+(\\d+)\\.ipa$"  # group 1 = buildVersion; no match → key omitted
max_versions = 0                 # 0 = unlimited; caps after sorting (newest first)

[news]
enabled = true
title_template = "{name} {version}"
max_entries = 0                  # 0 = unlimited; caps after sorting

[output]
path = "apps.json"               # resolved against THIS file's directory
```

### Behavior notes

- Versions are sorted newest-first by `(date, version)`; one version entry
  per matching release asset (a release with several IPAs produces several
  entries sharing the same version).
- A release with no matching asset contributes nothing — not even a news
  entry. One news entry is emitted per release that has assets.
- Empty output (no releases, only drafts, …) is a valid source: altgen
  warns on stderr and exits 0.

## CLI

```
altgen [-c PATH] [--repo OWNER/REPO] [--token TOKEN]
       [--name] [--subtitle] [--description] [--icon-url] [--website] [--tint-color]
       [--app-name] [--bundle-id] [--developer-name] [--app-subtitle]
       [--app-description] [--app-icon-url] [--app-tint-color] [--min-os-version]
       [--screenshots URL …] [--include-prereleases] [--max-versions N]
       [-o PATH] [-q] [-v] [--version]
```

- Without `-c`, `--repo`, `--app-name`, and `--bundle-id` are required.
- CLI flags override TOML values; `-o` resolves against the current
  directory while `[output] path` resolves against the config file's
  directory (so a config next to its sources works from any CWD).
- `-v` logs skipped releases (draft / prerelease / no matching assets) to
  stderr; `-q` silences the success message.
- Exit codes: `0` success, `1` GitHub or write error, `2` usage or config
  error.

## Development

```sh
pip install -e ".[dev]"
pytest            # fully offline — fixtures captured from the GitHub API
```
