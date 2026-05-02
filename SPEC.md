# SPEC: stac-check-action

## Overview
Unofficial composite GitHub Action to run `stac-check` (from [stac-utils/stac-check](https://github.com/stac-utils/stac-check)) against local STAC files. Assumes Python/pip are pre-installed on the runner (Python installation is out of scope for this action).

## Design Principles
- **Composite Action**: No container/JavaScript overhead, direct runner command execution.
- **Immutable Releases**: Action versions pinned to SHA tags; `stac-check` version user-specified (supply chain control). Use `latest` only for non-critical workflows.
- **Low Dependencies**: Zero external GitHub Actions; only runner-native tools (Python, pip, shell).
- **Tight Security**: No third-party deps, minimal permissions, user-controlled supply chain.

## Action Specification
Defined in `action.yml` (composite).

### Inputs
| Name | Required | Default | Description |
|------|----------|---------|-------------|
| `stac-check-version` | Yes | None | `stac-check` PyPI version (e.g., `1.9.1` or `v1.9.1`; leading `v` stripped) or `latest` |
| `file` | Yes | None | Path to local STAC file to validate |
| `recursive` | No | `false` | Recursively validate related local STAC objects (`--recursive`) |
| `max-depth` | No | `""` | Maximum recursion depth (`--max-depth`); ignored if `recursive` is false |
| `validate-assets` | No | `false` | Validate assets locally (`--assets --no-assets-urls`) |
| `pydantic` | No | `false` | Use stac-pydantic for enhanced validation (`--pydantic`) |
| `verbose` | No | `false` | Show verbose error messages (`--verbose`) |
| `fast` | No | `false` | Fast validation with FastJSONSchema, no geometry/linting (`--fast`) |
| `fast-linting` | No | `false` | Fast validation with linting, no geometry checks (`--fast-linting`) |
| `output-file` | No | `""` | Save CLI output to file (`--output`); requires `recursive: true` |
| `config` | No | `""` | Path to config file or inline YAML (sets `STAC_CHECK_CONFIG`) |
| `extra-args` | No | `""` | Additional `stac-check` CLI arguments (appended last) |
| `job-summary` | No | `true` | Write validation results to GitHub job summary |
| `comment-pr` | No | `false` | Post validation summary as PR comment (requires `pull-requests: write`) |

### Outputs
| Name | Description |
|------|-------------|
| `exit-code` | Exit code of `stac-check` command (0=valid, non-zero=issues found) |
| `output-file` | Path to file containing CLI output (if `output-file` input set) |

### Steps
1. **Install stac-check**:
   - If `stac-check-version` is `latest`: `pip install stac-check`
   - Else: strip leading `v` if present, then `pip install stac-check==<version>`
   - Fails immediately if Python/pip are unavailable.

2. **Build CLI arguments**:
   Construct the `stac-check` command with all enabled flags. Arguments are added in this order:
   - `--recursive` (if enabled)
   - `--max-depth N` (if set and recursive enabled)
   - `--assets` (if `validate-assets` is true; local-only, no network requests)
   - `--pydantic` (if enabled)
   - `--verbose` (if enabled)
   - `--fast` or `--fast-linting` (mutually exclusive; `--fast` takes precedence)
   - `--output FILE` (if `output-file` is set)
   - `extra-args` (appended last; users can pass `--assets` without local-only restriction if remote checks desired)
   - `config` handling (see below)
   - `file` (positional, always last)

**Config handling:**
- If `config` input is valid filepath: set `STAC_CHECK_CONFIG=/path/to/file`
- If `config` input contains newlines (inline YAML): write to `$RUNNER_TEMP/stac-check-config.yml`, set `STAC_CHECK_CONFIG=$RUNNER_TEMP/stac-check-config.yml`
- If empty: no action

3. **Run stac-check and capture output**:
   ```bash
    stac-check [all-flags] ${{ inputs.file }} > $RUNNER_TEMP/stac-check-output.txt 2>&1
    EXIT_CODE=$?
    echo "exit-code=$EXIT_CODE" >> $GITHUB_OUTPUT
    ```

4. **Write to job summary** (if `job-summary` is true):
    ```bash
    echo "## stac-check Results" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
    cat $RUNNER_TEMP/stac-check-output.txt >> $GITHUB_STEP_SUMMARY
    ```

5. **Post PR comment** (if `comment-pr` is true and event is pull_request):
    Use GitHub CLI to post comment with output content.

6. **Fail on issues** (if exit code is non-zero):
   ```bash
   if [ $EXIT_CODE -ne 0 ]; then
     echo "stac-check found validation issues (exit code: $EXIT_CODE)"
     exit $EXIT_CODE
   fi
   ```

### Permissions
Minimal permissions by default. Additional permissions required only when `comment-pr: true`:
```yaml
permissions:
  pull-requests: write  # Only if comment-pr: true
```

### Failure Behavior
Action fails (sets step exit code) when `stac-check` returns non-zero exit code, indicating validation issues or errors. Use `continue-on-error: true` in workflow if validation failures should not block the workflow.

## Security Considerations
- No external action dependencies to vet (composite action with runner-native tools only).
- Users must specify exact `stac-check` versions (avoids mutable/latest pulls).
- Minimal permissions by default; `pull-requests: write` only when `comment-pr: true`.
- No secret handling or privilege escalation.
- No network access required (local files only); `network: none` recommended in workflow.
- Output captured from stdout/stderr only; no injection vectors in CLI argument construction.

## Usage Example
Basic validation with job summary (enabled by default):
```yaml
name: Validate STAC
on: [push]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: lowlydba/stac-check-action@v1.0.0
        with:
          stac-check-version: 1.9.1
          file: ./stac/item.json
```

With PR comment and fast validation:
```yaml
name: Validate STAC
on:
  pull_request:
    paths: ['**/*.json']

jobs:
  validate:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write  # Required for comment-pr
    steps:
      - uses: actions/checkout@v4
      - uses: lowlydba/stac-check-action@v1.0.0
        with:
          stac-check-version: 1.9.1
          file: ./stac/collection.json
          fast-linting: true
          comment-pr: true
          validate-assets: true
```

With recursive validation and custom output:
```yaml
name: Validate STAC Collection
on: [push]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: lowlydba/stac-check-action@v1.0.0
        with:
          stac-check-version: 1.9.1
          file: ./catalog.json
          recursive: true
          max-depth: 3
          job-summary: true
          output-file: ./stac-check-results.txt
```

## Release Process
1. Tag commits with immutable semantic versions (e.g., `v1.0.0`) pointing to fixed SHAs.
2. Update major version tags (e.g., `v1`) only for breaking changes.
3. Document supported `stac-check` versions in README.

## Assumptions
- Runner has Python 3.10+ and pip pre-installed (out of scope for this action).
- `stac-check` version exists on PyPI and supports Python 3.10+.
- `GITHUB_STEP_SUMMARY` environment variable is available (GitHub Actions runner default).
- For `comment-pr`: workflow has `pull-requests: write` permission and runs on `pull_request` event.
- STAC files are local to the runner (fetched via `actions/checkout` or generated in workflow).
