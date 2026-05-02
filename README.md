# stac-check-action

Unofficial composite GitHub Action to run [stac-check](https://github.com/stac-utils/stac-check) against local STAC files. Validates, lints, and checks best practices for STAC items, collections, and catalogs.

## Features

- **Local-only validation** - No network access required; validates STAC files checked out in the workflow
- **Job summary** - Results automatically written to GitHub job summary (enabled by default)
- **PR comments** - Optional validation summary posted as pull request comments
- **Full CLI support** - All local validation flags: recursive, fast mode, pydantic validation, asset checks
- **Zero external dependencies** - Composite action using only runner-native tools (Python/pip)
- **Immutable releases** - Pin action and `stac-check` versions for reproducible builds

## Quick Start

```yaml
name: Validate STAC
on: [push]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: your-org/stac-check-action@v1.0.0
        with:
          stac-check-version: v1.14.0
          file: ./stac/item.json
```

## Inputs

| Name | Required | Default | Description |
|------|----------|---------|-------------|
| `stac-check-version` | Yes | - | Exact version (e.g., `v1.14.0`) or `latest` for newest release |
| `file` | Yes | - | Path to local STAC file to validate |
| `recursive` | No | `false` | Recursively validate related local STAC objects |
| `max-depth` | No | `""` | Maximum recursion depth (requires `recursive: true`) |
| `validate-assets` | No | `false` | Validate assets locally (no network) |
| `pydantic` | No | `false` | Use stac-pydantic for enhanced validation |
| `verbose` | No | `false` | Show verbose error messages |
| `fast` | No | `false` | Fast validation (no geometry/linting) |
| `fast-linting` | No | `false` | Fast validation with linting (no geometry) |
| `output-file` | No | `""` | Save CLI output to file |
| `job-summary` | No | `true` | Write results to GitHub job summary |
| `comment-pr` | No | `false` | Post results as PR comment (requires `pull-requests: write`) |
| `extra-args` | No | `""` | Additional CLI arguments |

## Outputs

| Name | Description |
|------|-------------|
| `exit-code` | Exit code from `stac-check` (0=valid, non-zero=issues) |

## Example: PR Comment with Fast Validation

```yaml
name: Validate STAC
on:
  pull_request:
    paths: ['**/*.json']

jobs:
  validate:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: your-org/stac-check-action@v1.0.0
        with:
          stac-check-version: v1.14.0
          file: ./stac/collection.json
          fast-linting: true
          comment-pr: true
          validate-assets: true
          config: .github/stac-check-config.yml
```

## Example: Inline Config

```yaml
      - uses: your-org/stac-check-action@v1.0.0
        with:
          stac-check-version: v1.14.0
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

## Full Specification

See [SPEC.md](./SPEC.md) for complete technical details.

## License

MIT
