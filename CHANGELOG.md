# Changelog

All notable changes to this project are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Breaking:** Rustac is the only validation backend. Validation covers core and declared extension JSON Schemas, without stac-check linting, best-practice checks, stac-pydantic, or geometry topology checks.
- Pin the rustac PyPI package with `rustac-version` (default `0.9.17`). Python 3.11+ is required.
- Traverse local JSON and map published absolute links to local files, avoiding catalog HTTP requests. Batch Items in one Rust process and validate Catalogs/Collections with bounded concurrency.
- `exit-code` is an aggregate 0/1 status. Root depth is zero; output-file works without recursion.
- **Breaking:** Remove the stac-check-version, config, pydantic, fast, and fast-linting inputs. Stac-check CLI flags aren't supported.
- Deterministic composite tests and real-CLI integration tests supplement a current-generator Overture sample-catalog test against public data. Linux/Windows unit CI measures branches and requires 95% combined coverage.

### Migration from v1

Replace `stac-check-version` with `rustac-version` and review which checks your workflow requires. Remove `config`, `pydantic`, `fast`, and `fast-linting` settings. Remove stac-check flags from extra-args. Rustac is the only supported backend.

Other input names stay the same. Output-file works without recursion; exit-code is an aggregate 0/1 status, and max-depth counts the root as zero.

For workflows requiring stac-check's linting or configuration, keep the immutable v1 release SHA or run that tool separately. Roll back by restoring that SHA and its v1 inputs.

### Added

- File-attributed GitHub error annotations, compact errors, raw verbose diagnostics, and failing-batch isolation.
- Item coordinate-range and geometry/bbox consistency checks on original JSON, covering all geometry types, 2D/3D bounds, absolute floating-point tolerances, and antimeridian-cut components.
- Shapely handles geometry parsing, coordinate extraction, and component bounds; validation doesn't repair input geometries.
- JSON and Markdown reports exposed as report-path and summary-path, with counts, timings, scope, and errors shared by step summaries and sticky PR comments.

## [1.0.0]

### Added

- Initial release of `stac-check-action`.
- Composite GitHub Action wrapping [`stac-check`](https://github.com/stac-utils/stac-check).
- Inputs: `stac-check-version`, `file`, `recursive`, `max-depth`, `validate-assets`, `pydantic`, `verbose`, `fast`, `fast-linting`, `output-file`, `config`, `extra-args`, `job-summary`, `comment-pr`.
- Outputs: `valid`, `exit-code`, `log-path`.
- Sticky PR comment via hidden HTML marker. Updates instead of stacking. Comment lookup paginates to handle busy PRs.
- Job summary with fenced "Validation Summary" section.
- Local-only validation by default. `--no-assets-urls` enforced when `validate-assets: true`.
- Output-marker parsing for `valid`. Compensates for unreliable upstream exit codes in recursive mode.
- Hardened workflows: top-level `permissions: {}`, per-job scoping, SHA-pinned actions, zizmor and actionlint in CI, dependabot for github-actions ecosystem.
- BATS unit tests for `scripts/run.sh`.

[Unreleased]: https://github.com/OvertureMaps/stac-check-action/commits/main
[1.0.0]: https://github.com/OvertureMaps/stac-check-action/releases/tag/v1.0.0
