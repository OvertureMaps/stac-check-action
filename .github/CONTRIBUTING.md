# Contributing

Read [SPEC.md](../SPEC.md) before changing validation behavior. Schema rules come from upstream; the wrapper also checks coordinate ranges and geometry/bbox consistency.

## Setup and tests

Use Python 3.11+:

```bash
python -m pip install -r requirements-test.txt rustac==0.9.17
python -m coverage run --branch --source=scripts -m unittest discover -s tests -p "test_*.py"
python -m coverage report --fail-under=95 --show-missing
RUN_INTEGRATION=1 python -m unittest discover -s tests -p test_integration.py -v
```

In PowerShell, set `$env:RUN_INTEGRATION='1'` before the integration command. Extension integration tests require network access to their declared schemas.

Run the wrapper against generated or checked-out files:

```bash
IN_FILE=./stac/catalog.json IN_RECURSIVE=true python scripts/run.py
```

The wrapper publishes reports before the composite action's final step raises validation failures. Inspect its report or valid output for the validation result, not its own process exit code.

CI runs unit coverage, real rustac integration tests, YAML validation, line-ending checks, zizmor, and composite-action tests. The deterministic catalog fixture provides stable success and failure cases. A separate required job installs the published overture-stac 4.0.0 crate and generates a catalog against the public bucket in sample mode (one Item per Collection). It validates the catalog with this action, checks that traversal discovers every generated JSON object, and logs the installed generator version. Public data and network failures can fail that job. Test both errors and success paths when changing the wrapper.

## Pull requests

Discuss substantial changes in an issue first. Update README, SPEC, and the Unreleased changelog section when behavior changes. Use LF line endings, 2-space YAML indentation, and Conventional Commits. Pin remote GitHub Actions to full commit SHAs with release comments.

Releases are maintainer-only semantic versions with immutable tags.
