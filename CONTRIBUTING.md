# Contributing

Thanks for considering a contribution.

## Ground rules

- Read [SPEC.md](./SPEC.md) before proposing changes. Design constraints are intentional: composite only, zero external action deps, local-only by default.
- Discuss substantial changes in an issue before opening a PR.
- All PRs must pass CI: matrix tests, lint, zizmor, actionlint, BATS unit tests, e2e.
- Follow existing code style: LF line endings, 2-space YAML indent.

## Local setup

```bash
git clone https://github.com/lowlydba/stac-check-action.git
cd stac-check-action
pip install stac-check==1.9.1   # or pin to whatever you're testing against
```

## Testing locally

Validate `action.yml` parses:

```bash
python -c "import yaml; yaml.safe_load(open('action.yml'))"
```

Run the action's logic against a local STAC file:

```bash
stac-check ./path/to/item.json
```

Run the BATS unit tests for `scripts/run.sh` (requires Node/npm; pinned in CI):

```bash
npx -y bats@1.13.0 tests/
```

Run zizmor (requires [installation](https://docs.zizmor.sh/installation/)):

```bash
GITHUB_TOKEN=$(gh auth token) zizmor .
```

Run actionlint:

```bash
actionlint
```

## Pull request checklist

- [ ] Branch from `main`
- [ ] One logical change per PR
- [ ] CHANGELOG.md updated under `[Unreleased]`
- [ ] SPEC.md updated if behavior changes
- [ ] README.md updated if user-facing
- [ ] CI green (zizmor + actionlint + matrix tests + BATS + e2e)
- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/) format

## Commit message format

```
type(scope): short description

Longer body if needed.
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `perf`.

## Releasing

Maintainers only. See [SPEC.md § Release Process](./SPEC.md#release-process).

## Code of conduct

This project adheres to the [Contributor Covenant](./CODE_OF_CONDUCT.md). By participating, you agree to its terms.
