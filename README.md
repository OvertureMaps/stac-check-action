# stac-check-action

[![CI](https://github.com/OvertureMaps/stac-check-action/actions/workflows/ci.yml/badge.svg)](https://github.com/OvertureMaps/stac-check-action/actions/workflows/ci.yml)

Catch catalog errors before publishing your STAC. Validate Catalogs, Collections, and Items with [rustac](https://github.com/stac-utils/rustac), then check Item coordinate ranges and bounding boxes with Shapely-backed geometry checks.

Built for generated catalogs with thousands of Items: schema validation batches Items into one Rust process, reusing compiled extension schemas. The action checks your build's JSON without downloading the published catalog.

- ⚡ **Rust-powered schema validation:** core STAC and declared extensions, with no Rust toolchain required on your runner.
- 📐 **Spatial consistency:** longitude/latitude ranges and geometry/bbox agreement, including elevation and antimeridian-cut geometries.
- 📋 **Results where you work:** source-file annotations, GitHub step summaries, optional sticky PR comments, and machine-readable JSON reports.

## Usage

Use this configuration with the commit SHA of the v2 release once published:

```yaml
jobs:
  validate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: OvertureMaps/stac-check-action@<full-v2-commit-sha>
        with:
          rustac-version: '0.9.17'
          file: ./stac/catalog.json
          recursive: true
```

The action requires Python 3.11+, pip, and bash. The rustac PyPI package includes the Rust CLI, so runners don't need Cargo or a Rust build. Its package version differs from the embedded CLI version.

## Inputs

| Input | Default | Behavior |
|---|---|---|
| `file` | Required | Local path to a Catalog, Collection, or Item JSON file. |
| `rustac-version` | `0.9.17` | PyPI package version. A leading `v` is stripped; `latest` is permitted but isn't reproducible. |
| `recursive` | `false` | Validate linked child catalogs, collections, and items. |
| `max-depth` | ∞ | Non-negative traversal depth. Root is depth 0; 0 checks only the root. Ignored without recursion. |
| `validate-assets` | `false` | Check local asset file existence, not content or remote availability. |
| `verbose` | `false` | Include raw rustac stdout/stderr for failures in the log. |
| `output-file` | Empty | Copy the validation log to this path. Parent directory must exist. |
| `stream-output` | `true` | Print wrapper progress and failures as they occur; false prints the captured log at completion. |
| `job-summary` | `true` | Publish counts, elapsed time, scope, and file-attributed errors to the GitHub step summary. |
| `comment-pr` | `false` | Publish the same summary as a sticky PR comment. Requires a pull_request event and `pull-requests: write`. |
| `extra-args` | Empty | Quoted arguments parsed without a shell. Only rustac verbosity flags (`-v`, `--verbose`, `-q`, `--quiet`) are supported. |

## Outputs and reports

| Output | Meaning |
|---|---|
| `valid` | true when all checks on discovered local objects pass. Skipped remote targets aren't validated. |
| `exit-code` | Aggregate result: 0 for success, 1 for schema, input, filesystem, or CLI errors. It isn't a raw single-process exit code. |
| `log-path` | UTF-8 validation log, created before input validation. |
| `summary-path` | Markdown report shared by the step summary and PR comment. |
| `report-path` | JSON report with counts, timing, and an `errors` array of `{file, message}` objects. |

Reports remain available after validation failures. Use `continue-on-error: true` when consuming failures as outputs. Installation failures occur before the runner and have no report outputs.

Step summaries and PR comments include counts, timing, and errors with source filenames. Full collected errors remain in the log and JSON report when the summary is truncated. Enable verbose for raw rustac diagnostics.

## Validation scope

### What gets checked

| Check | Coverage |
|---|---|
| STAC schemas | Catalog, Collection, and Item core schemas, plus extensions declared in each object's `stac_extensions`. |
| Coordinate ranges | Finite coordinates; longitude within ±180° and latitude within ±90°. No guessing whether coordinates are swapped. |
| Item bounding boxes | Geometry/bbox extrema agree in 2D or 3D, including elevation. Absolute tolerances are 5e-7 degrees horizontally and 1e-6 meters vertically. |
| Geometry types | Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon, and nested GeometryCollections. |
| Antimeridian bounds | Wrapped bboxes (west > east) must contain whole geometry components and match their bounds. Wide non-crossing geometries and global bounds are also supported. |
| Catalog traversal | Follow child/item links when recursion is enabled; missing local targets and unreadable JSON fail the run. |
| Asset references | Optionally check that referenced local asset files exist. |

Spatial checks run on the original Item JSON. Shapely parses geometries and computes bounds without repairing them. Segments use GeoJSON's straight Cartesian interpolation: a LineString from 170° to -170° isn't silently reinterpreted as a short dateline crossing. Use antimeridian-cut components when representing that crossing.

Provide a checked-out or generated JSON catalog. Published URLs within its root self-link directory resolve to the corresponding local files; other remote targets are skipped with a warning. Extension schemas can require network access.

### Boundaries and future work

This validates catalog metadata, not the geospatial assets themselves. It doesn't open COGs or GeoParquet, inspect their CRS, or compare their actual footprints with Item geometry. It also doesn't check remote URL availability, polygon topology (such as self-intersections), ring winding, geodesic bounds, or whether a Collection's extent contains every Item.

Schema checks use rustac's deserialized STAC values, which can normalize optional fields. A passing result therefore isn't a guarantee that the original JSON satisfies every schema constraint without normalization. Geometry/bbox checks establish consistency, not that the footprint describes the right place on Earth.

Best-practice linting is tracked in [OvertureMaps/stac-check-action#17](https://github.com/OvertureMaps/stac-check-action/issues/17), including metadata completeness, identifiers, and filename conventions. Those recommendations aren't checks today. Other capabilities above are outside the current scope, not promised features.

See [validation boundaries](./SPEC.md#validation-boundaries) for the detailed geometry policy.

## Permissions and pinning

Pin this action to a full commit SHA and rustac-version to an exact package version. Released tags are immutable under the repository's [release ruleset](https://github.com/OvertureMaps/stac-check-action/rules). `latest` is suitable only when upstream changes are acceptable.

No extra permissions are needed for local validation beyond those needed to check out your repository. PR comments require `pull-requests: write`; the action doesn't elevate permissions. Use trusted workflows and inputs: JSON Schemas declared by the catalog can trigger outbound requests from rustac.

See [SPEC.md](./SPEC.md) for runner behavior, [CONTRIBUTING.md](./.github/CONTRIBUTING.md) for tests, and [SECURITY.md](./.github/SECURITY.md) for vulnerability reporting.
