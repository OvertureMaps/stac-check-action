# stac-check-action

[![CI](https://github.com/lowlydba/stac-check-action/actions/workflows/ci.yml/badge.svg)](https://github.com/lowlydba/stac-check-action/actions/workflows/ci.yml) [![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/lowlydba/stac-check-action/ci.yml)](https://github.com/lowlydba/stac-check-action/actions/workflows/ci.yml) [![immutable release ruleset](https://img.shields.io/badge/immutable%20tags-active-green?logo=github)](https://github.com/lowlydba/stac-check-action/rules) [![stac-check-action](https://img.shields.io/badge/stac--check--action-🎯-blue?style=flat)](https://github.com/lowlydba/stac-check-action)

A lightweight composite GitHub Action that runs [`stac-check`](https://github.com/stac-utils/stac-check) against local STAC (SpatioTemporal Asset Catalog) files to validate, lint, and check best practices for STAC items, collections, and catalogs.

- 🔒 action dependency-free (composite, no external actions)
- ⚛️ small size (runner-native tools only)
- 🌎 local-only (no network access required)

### Why local-only?

STAC catalogs often reference remote assets and links via URLs. By default, this action only validates local files checked out in your repository and never makes network requests to resolve remote URLs. This keeps CI runs fast, deterministic, and secure:

- No waiting on external servers or CDNs to respond
- Validation won't fail because of transient network issues or remote servers being down
- No risk of unexpected outbound requests from your CI runner
- Works on air-gapped or restricted runners without internet access

Asset validation (`validate-assets: true`) also only checks local file paths, using `--no-assets-urls` under the hood to skip URL-based assets. If you need to validate remote URLs, pass `--assets` directly via `extra-args` to opt in.

---

- [stac-check-action](#stac-check-action)
    - [Why local-only?](#why-local-only)
  - [Usage](#usage)
  - [Inputs](#inputs)
  - [Outputs](#outputs)
  - [Example: PR Comment](#example-pr-comment)
  - [Example: Inline Config](#example-inline-config)
  - [Requirements](#requirements)
  - [Security](#security)
  - [Show Your Support](#show-your-support)
  - [Full Specification](#full-specification)
  - [About](#about)
  - [License](#license)

## Usage

Add this step after checking out your repository:

```yaml
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
      - uses: lowlydba/stac-check-action@v1.0.0
        with:
          stac-check-version: 1.9.1
          file: ./stac/item.json
```

### Pinning

For supply-chain-sensitive workflows, pin to a commit SHA instead of a tag:

```yaml
- uses: lowlydba/stac-check-action@<full-commit-sha> # v1.0.0
```

Tags are immutable per this repo's [release ruleset](https://github.com/lowlydba/stac-check-action/rules), but SHA pinning gives the strongest guarantee against upstream tampering. [Dependabot](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/keeping-your-actions-up-to-date-with-dependabot) keeps SHA-pinned actions current automatically.

For PR comments with fast validation:

```yaml
jobs:
  validate:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
      - uses: lowlydba/stac-check-action@v1.0.0
        with:
          stac-check-version: 1.9.1
          file: ./stac/collection.json
          fast-linting: true
          comment-pr: true
          validate-assets: true
```

## Inputs

| Input | Description | Allowed Values | Default |
|-------|-------------|----------------|---------|
| `stac-check-version` **(required)** | Exact version (e.g. `1.9.1`) or `latest` for newest release | `string` | — |
| `file` **(required)** | Path to local STAC file to validate | `string` | — |
| `recursive` | Recursively validate related local STAC objects | `'true'` or `'false'` | `'false'` |
| `max-depth` | Maximum recursion depth (requires `recursive: true`) | `integer` | — |
| `validate-assets` | Validate assets locally (no network requests) | `'true'` or `'false'` | `'false'` |
| `pydantic` | Use stac-pydantic for enhanced validation | `'true'` or `'false'` | `'false'` |
| `verbose` | Show verbose error messages | `'true'` or `'false'` | `'false'` |
| `fast` | Fast validation with FastJSONSchema, no geometry/linting | `'true'` or `'false'` | `'false'` |
| `fast-linting` | Fast validation with linting, no geometry checks | `'true'` or `'false'` | `'false'` |
| `output-file` | Save CLI output to file (requires `recursive: true`) | `string` | — |
| `config` | Path to config file or inline YAML (sets `STAC_CHECK_CONFIG`) | `string` | — |
| `job-summary` | Write results to GitHub job summary | `'true'` or `'false'` | `'true'` |
| `comment-pr` | Post results as PR comment (requires `pull-requests: write`) | `'true'` or `'false'` | `'false'` |
| `extra-args` | Additional CLI arguments (appended last) | `string` | — |

## Outputs

| Name | Description |
|------|-------------|
| `exit-code` | Exit code from stac-check (0=valid, non-zero=issues) |
| `output-file` | Path to file containing CLI output (if `output-file` input set) |
| `output-path` | Path to captured stac-check stdout/stderr (always set) |
| `valid` | `true` if stac-check output contained no failure markers, else `false` |

## Example: PR Comment

```yaml
      - uses: lowlydba/stac-check-action@v1.0.0
        with:
          stac-check-version: 1.9.1
          file: ./stac/collection.json
          fast-linting: true
          comment-pr: true
          config: .github/stac-check-config.yml
```

## Example: Inline Config

```yaml
      - uses: lowlydba/stac-check-action@v1.0.0
        with:
          stac-check-version: 1.9.1
          file: ./item.json
          config: |
            linting:
              check_geometry: false
              bloated_links: true
            settings:
              max_links: 10
```

## Requirements

- Runner with Python 3.10+ and pip pre-installed
- `stac-check` version must exist on PyPI and support Python 3.10+

## Security

- No external action dependencies
- Minimal permissions (only `pull-requests: write` if using `comment-pr`)
- No network access required (local files only)
- Users specify exact versions (use `latest` only for non-critical workflows)

## Show Your Support

Add a badge to your repository:

[![stac-check-action](https://img.shields.io/badge/stac--check--action-🎯-blue?style=flat)](https://github.com/lowlydba/stac-check-action)

```markdown
[![stac-check-action](https://img.shields.io/badge/stac--check--action-🎯-blue?style=flat)](https://github.com/lowlydba/stac-check-action)
```

## Full Specification

See [SPEC.md](./SPEC.md) for complete technical details.

## About

🎯 GitHub Action that runs stac-check for local STAC file validation, linting, and best practices compliance.

[github.com/marketplace/actions/stac-check-action](https://github.com/marketplace/actions/stac-check-action)

## License

[MIT](./LICENSE)
