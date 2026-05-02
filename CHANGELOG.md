# Changelog

All notable changes to this project are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/lowlydba/stac-check-action/commits/v1
