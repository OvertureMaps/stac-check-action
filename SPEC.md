# Specification

## Scope

Composite GitHub Action using the rustac PyPI distribution's Rust CLI. Python 3.11+, pip, and bash are runner prerequisites; gh is needed only for PR comments. No container, JavaScript runtime, or external action dependencies are required. See [README.md](./README.md) for the input/output contract and [CHANGELOG.md](./CHANGELOG.md) for migration guidance.

## Execution

1. Install the exact rustac package version with `python -m pip`. Strip a leading v; latest opts into an unpinned package. Log both the installed package version and the embedded CLI version.
2. Run `scripts/run.py` with inputs supplied through environment variables, not interpolated shell commands.
3. Create a unique report directory beneath RUNNER_TEMP and publish log-path before checking inputs.
4. Check supported input values and reject unsafe CLI format/input overrides with explicit diagnostics.
5. Traverse local child/item links breadth-first. Root depth is zero. Canonical paths deduplicate references and break cycles. Read errors and malformed JSON are failures, not skipped objects.
6. Resolve relative links against their source files. Map HTTP(S) links under the root self-link directory into the local root directory, rejecting encoded traversal outside it. Unmapped remote links are skipped with a warning. Missing mapped files fail; no network fallback occurs.
7. Optionally check local asset file existence. Remote assets aren't fetched. Unsupported object-store schemes on traversal links fail explicitly.
8. Check Item coordinate ranges and geometry/bbox consistency against the original JSON. Serialize Items as NDJSON in a temporary file and validate them in one process. Validate Catalogs and Collections individually with up to four concurrent processes. Each invocation uses fixed input/output formats and a 120-second timeout.
9. Split failing Item batches only when rustac supplies structured object errors or its recognized deserialization error. Other failures stop isolation and fail the run, avoiding repeated requests for shared operational errors. IDs don't identify files uniquely. Temporary batch files are deleted even when rustac fails or times out.
10. Interpret nonzero process status as a failure. Parse structured CLI errors when available; retain plain diagnostics otherwise. Replace leading instance JSON with a compact marker, and supply filename and parse troubleshooting guidance. Verbose logs retain raw diagnostics.
11. Publish JSON and Markdown reports and aggregate valid/exit-code outputs, including operational failures. Copy the log to output-file when requested.
12. Publish the Markdown summary and optional sticky PR comment before the final step fails validation. Publication steps log success or why there's nothing to publish, including disabled options and absent reports. The final step logs success or failure explicitly. Installation failures have no runner reports.

## Reports

JSON contains backend, valid, objects, items, collections, catalogs, errors, skipped_remote, checked_assets, cli_calls, and seconds. Objects counts discovered JSON objects, not a guarantee that every object was validated if an operational error interrupts the run. Errors contain file and message strings. Remote counts represent references, not unique URLs.

Markdown includes counts, elapsed time, validation scope, skipped remote references, checked local assets, and at most 50 errors. A text budget keeps the summary within GitHub's PR comment limit. Messages in Markdown and annotations are capped at 2,000 characters; the JSON report and log contain all collected errors. Filenames and errors are escaped for their destination, so catalog content can't create workflow commands or HTML.

The wrapper returns zero after publishing an unsuccessful result. The composite's final step fails on a nonzero aggregate exit-code or valid=false. Unexpected runner termination or absent outputs also fails the action.

## Validation boundaries

The upstream Rust validator owns core and declared extension schema checks. No local STAC schemas, lint rules, best-practice rules, or geometric topology checks are implemented here. Rustac validates deserialized values, which can normalize optional/default fields; this isn't strict raw-JSON schema validation.

Item geometry checks use [GeoJSON's coordinate and bbox model](https://www.rfc-editor.org/rfc/rfc7946.html#section-5): "The axes order of a bbox follows the axes order of geometries." Shapely parses the geometry, extracts coordinates, and computes component bounds without repair. All seven geometry types, including nested GeometryCollections, are supported. Coordinates must be finite numbers with longitude in [-180, 180] and latitude in [-90, 90]. Two- and three-dimensional positions are supported; mixed dimensions fail explicitly. Elevation isn't subject to a geographic range restriction. Schema validation remains responsible for structural requirements that Shapely's parser accepts permissively.

Bbox comparisons require matching coordinate extrema, with absolute tolerances of 5e-7 degrees and 1e-6 meters for elevation; no relative tolerance is used. Southern/northern and lower/upper elevation bounds must be ordered. A geometry without a bbox receives coordinate checks only; a null geometry is left to schema validation. Empty geometries have no calculable bounds and fail when supplied a bbox.

Longitude matching accepts an ordinary min/max envelope, including valid envelopes wider than 180 degrees and world bounds. Wrapped bboxes (west > east) must contain each whole connected component in one of their longitude intervals and match the outer component extrema. GeoJSON segments interpolate longitude directly; a segment between 170 and -170 isn't silently interpreted as crossing the antimeridian. Cut geometries can use a wrapped envelope or their ordinary coordinate envelope. Polygon holes contribute elevation extrema. Ring validity, self-intersections, winding, spherical/geodesic bounds, coordinate-order guessing, and Collection extent aggregation aren't checked.

Core schemas are bundled for supported STAC versions. Extension schemas and referenced resources can require network requests. The Items batch shares a validator cache; independent container invocations don't. Repeated failure isolation can cost more subprocesses and schema downloads than a passing run.

Remote targets outside the local mapping aren't checked, and a passing local report doesn't imply they are valid. Schema retrieval errors, subprocess timeouts, missing files, and malformed inputs fail explicitly.

Link-resolution errors don't stop traversal of sibling links. Container subprocess failures are recorded per file without discarding other container results. An operational Item-batch failure stops the run with an explicit incomplete-validation error.

## CI

Unit tests exercise traversal, aliases/cycles/depth, malformed input, assets, CLI contracts, batching and failure isolation, escaping, invalid inputs, operational failures, logs, and reports. Branch measurement is enabled with a minimum combined coverage of 95%.

Real-CLI integration tests cover a large local catalog, invalid structures, duplicate IDs, and extension schema rejection. Tests run on Linux and Windows with Python 3.11, 3.12, and 3.14. A composite-action job checks summaries and outputs for passing and failing inputs. All remote action references are SHA-pinned; self references use GitHub's secure `$/` syntax.

A separate required composite-action job builds the current Overture generator against the public data bucket in sample mode, covering one Item per Collection across available releases. It verifies that every generated JSON object is discovered and that validation and report publication succeed. This job depends on the current generator, public data, and schema availability; the generator commit is logged.
