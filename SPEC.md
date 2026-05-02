# SPEC: stac-check-action

Reference specification. For usage and examples see [README.md](./README.md).

## Overview

Composite GitHub Action that runs `stac-check` (from [stac-utils/stac-check](https://github.com/stac-utils/stac-check)) against local STAC files. Python and pip are assumed pre-installed on the runner; installing them is out of scope.

Design constraints:

- Composite action only. No container, no JavaScript runtime, no external action dependencies.
- Action versions pin to immutable SHA tags. The `stac-check` version is user-specified for supply-chain control.
- Runner-native tools only: Python, pip, bash, gh.

## Inputs

| Name | Required | Default | Description |
|------|----------|---------|-------------|
| `stac-check-version` | Yes | | `stac-check` PyPI version (e.g. `1.9.1` or `v1.9.1`; leading `v` stripped) or `latest`. |
| `file` | Yes | | Path to local STAC file to validate. |
| `recursive` | No | `false` | Recursively validate related local STAC objects (`--recursive`). |
| `max-depth` | No | `""` | Maximum recursion depth (`--max-depth`); ignored if `recursive` is false. |
| `validate-assets` | No | `false` | Validate assets locally (`--assets --no-assets-urls`). |
| `pydantic` | No | `false` | Use stac-pydantic (`--pydantic`). |
| `verbose` | No | `false` | Verbose error messages (`--verbose`). |
| `fast` | No | `false` | Fast validation, no geometry/linting (`--fast`). |
| `fast-linting` | No | `false` | Fast validation with linting, no geometry (`--fast-linting`). |
| `output-file` | No | `""` | Save CLI output to file (`--output`); requires `recursive: true`. |
| `config` | No | `""` | Path to config file or inline YAML; sets `STAC_CHECK_CONFIG`. |
| `extra-args` | No | `""` | Additional CLI arguments, appended last. |
| `job-summary` | No | `true` | Write results to GitHub job summary. |
| `comment-pr` | No | `false` | Post results as PR comment; requires `pull-requests: write`. |

## Outputs

| Name | Description |
|------|-------------|
| `valid` | Authoritative validation result. `true` if no failure markers found in output, else `false`. |
| `exit-code` | Raw `stac-check` CLI exit code. Not authoritative in recursive mode (upstream often returns 0 on failures); prefer `valid`. |
| `log-path` | Path to captured `stac-check` stdout/stderr. Created before input validation runs, so available on every invocation including early-exit errors. |

## Steps

1. Install `stac-check`. If `stac-check-version` is `latest`, run `pip install stac-check`. Otherwise strip a leading `v` and run `pip install stac-check==<version>`. Fails immediately if Python/pip are unavailable.

2. Build CLI arguments. Order:
   - `--recursive` (if enabled)
   - `--max-depth N` (if set and recursive enabled)
   - `--assets` (if `validate-assets`; local-only via `--no-assets-urls`)
   - `--pydantic` (if enabled)
   - `--verbose` (if enabled)
   - `--fast` or `--fast-linting` (mutually exclusive; `--fast` wins)
   - `--output FILE` (if `output-file` is set)
   - `extra-args` (raw, word-split)
   - `file` (positional, last)

3. Resolve config:
   - If `config` is an existing filepath: set `STAC_CHECK_CONFIG=/path/to/file`.
   - Else if value contains no `:` and no newline: error out. The value cannot be valid YAML and is treated as a missing path (typo guard).
   - Otherwise treat as inline YAML, write to a unique file under `$RUNNER_TEMP`, and set `STAC_CHECK_CONFIG` to that path.
   - If empty: no action.

4. Run `stac-check`:
   - Inputs are passed to the script via `env:` (no shell interpolation of `${{ }}` in `run:` bodies).
   - Args are built as a bash array and quoted on expansion.
   - Output is captured to a unique file under `$RUNNER_TEMP` exposed as `log-path`.
   - `exit-code` is set to the raw stac-check exit code.
   - `valid` is set to `false` if the output contains failure markers (see [Failure behavior](#failure-behavior)).

5. Job summary (if `job-summary: true`): the "Validation Summary" section (or full output if absent) is appended to `$GITHUB_STEP_SUMMARY` inside a fenced code block.

6. PR comment (if `comment-pr: true` and event is `pull_request`): posted via `gh pr comment` with `GH_TOKEN: ${{ github.token }}`. Sticky via a hidden HTML marker; existing comments are updated rather than stacked. Comment lookup paginates to handle busy PRs.

7. Fail step on validation failure (see [Failure behavior](#failure-behavior)).

## Permissions

Default minimal. Required additions:

| Feature | Permission |
|---------|------------|
| `comment-pr: true` | `pull-requests: write` |

## Failure behavior

The action fails the step in either case:

1. `stac-check` returned a non-zero exit code (re-raised verbatim).
2. `stac-check` returned 0 but the captured output contained failure markers:
   - `Recursive validation has failed!`
   - `Failed: N/M` with `N >= 1`
   - `Passed: False`
   - `Valid: False`

Marker parsing compensates for upstream recursive-mode behavior, where exit codes do not reliably reflect failures.

Use `continue-on-error: true` if you want failures to surface as outputs (`exit-code`, `valid`) without blocking the workflow.

## Security considerations

- No external action dependencies.
- All user inputs flow through `env:` blocks; no `${{ }}` interpolation in `run:` bodies. Mitigates shell injection.
- `extra-args` is word-split unquoted. Callers are responsible for safe content. This is the documented escape hatch.
- `latest` is allowed for `stac-check-version` but discouraged in production. Pin an exact version.
- Default permissions are minimal. `pull-requests: write` is only needed for `comment-pr: true`.
- No secret handling, no privilege escalation, no network access required for validation.

## Release process

1. Tag commits with semantic versions (e.g. `v1.0.0`) pointing to fixed SHAs. Release ruleset enforces tag immutability.
2. Document supported `stac-check` versions in `README.md`.

## Assumptions

- Runner has Python 3.10+ and pip.
- `stac-check` version exists on PyPI and supports Python 3.10+.
- `GITHUB_STEP_SUMMARY` is available (default on GitHub-hosted runners).
- `comment-pr` workflows have `pull-requests: write` and run on `pull_request` events.
- STAC files are local (checked out via `actions/checkout` or generated in workflow).
