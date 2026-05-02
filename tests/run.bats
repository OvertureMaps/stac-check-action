#!/usr/bin/env bats
# Unit tests for scripts/run.sh
# Uses tests/bin/stac-check (mock) injected via PATH.

setup() {
  TEST_TEMP="$(mktemp -d)"

  # GitHub Actions stubs
  export GITHUB_OUTPUT="$TEST_TEMP/github_output"
  touch "$GITHUB_OUTPUT"
  export RUNNER_TEMP="$TEST_TEMP/runner"
  mkdir -p "$RUNNER_TEMP"

  # Put mock stac-check first on PATH
  chmod +x "$BATS_TEST_DIRNAME/bin/stac-check"
  export PATH="$BATS_TEST_DIRNAME/bin:$PATH"

  # Mock control
  export MOCK_ARGS_FILE="$TEST_TEMP/mock_args"
  export MOCK_ENV_FILE="$TEST_TEMP/mock_env"
  export MOCK_EXIT_CODE=0

  # Default inputs (all optional flags off)
  export IN_FILE="$TEST_TEMP/item.json"
  export IN_RECURSIVE="false"
  export IN_MAX_DEPTH=""
  export IN_VALIDATE_ASSETS="false"
  export IN_PYDANTIC="false"
  export IN_VERBOSE="false"
  export IN_FAST="false"
  export IN_FAST_LINTING="false"
  export IN_OUTPUT_FILE=""
  export IN_EXTRA_ARGS=""
  export IN_CONFIG=""

  echo '{"type":"Feature"}' > "$IN_FILE"

  SCRIPT="$BATS_TEST_DIRNAME/../scripts/run.sh"
}

teardown() {
  rm -rf "$TEST_TEMP"
}

# ---------------------------------------------------------------------------
# Exit code recording
# ---------------------------------------------------------------------------

@test "exit-code=0 written to GITHUB_OUTPUT when stac-check exits 0" {
  MOCK_EXIT_CODE=0 run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "exit-code=0" "$GITHUB_OUTPUT"
}

@test "exit-code=2 written to GITHUB_OUTPUT when stac-check exits 2; script exits 0" {
  export MOCK_EXIT_CODE=2
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "exit-code=2" "$GITHUB_OUTPUT"
}

@test "log-path is always written to GITHUB_OUTPUT" {
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "log-path=" "$GITHUB_OUTPUT"
}

# ---------------------------------------------------------------------------
# Flag construction
# ---------------------------------------------------------------------------

@test "recursive:false — --recursive NOT passed" {
  export IN_RECURSIVE="false"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  ! grep -qx -- "--recursive" "$MOCK_ARGS_FILE"
}

@test "recursive:true — --recursive passed" {
  export IN_RECURSIVE="true"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -qx -- "--recursive" "$MOCK_ARGS_FILE"
}

@test "recursive:true + max-depth — --max-depth N passed" {
  export IN_RECURSIVE="true"
  export IN_MAX_DEPTH="3"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -qx -- "--recursive"  "$MOCK_ARGS_FILE"
  grep -qx -- "--max-depth"  "$MOCK_ARGS_FILE"
  grep -qx -- "3"            "$MOCK_ARGS_FILE"
}

@test "max-depth without recursive — --max-depth NOT passed" {
  export IN_RECURSIVE="false"
  export IN_MAX_DEPTH="3"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  ! grep -qx -- "--max-depth" "$MOCK_ARGS_FILE"
}

@test "validate-assets:true — --assets and --no-assets-urls passed" {
  export IN_VALIDATE_ASSETS="true"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -qx -- "--assets"         "$MOCK_ARGS_FILE"
  grep -qx -- "--no-assets-urls" "$MOCK_ARGS_FILE"
}

@test "pydantic:true — --pydantic passed" {
  export IN_PYDANTIC="true"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -qx -- "--pydantic" "$MOCK_ARGS_FILE"
}

@test "verbose:true — --verbose passed" {
  export IN_VERBOSE="true"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -qx -- "--verbose" "$MOCK_ARGS_FILE"
}

@test "fast:true — --fast passed" {
  export IN_FAST="true"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -qx -- "--fast" "$MOCK_ARGS_FILE"
}

@test "fast-linting:true — --fast-linting passed" {
  export IN_FAST_LINTING="true"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -qx -- "--fast-linting" "$MOCK_ARGS_FILE"
}

@test "fast:true + fast-linting:true — only --fast passed (fast wins)" {
  export IN_FAST="true"
  export IN_FAST_LINTING="true"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -qx  -- "--fast"         "$MOCK_ARGS_FILE"
  ! grep -qx -- "--fast-linting" "$MOCK_ARGS_FILE"
}

@test "extra-args word-split and appended as individual flags" {
  export IN_EXTRA_ARGS="--no-recursive --max-depth 5"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -qx -- "--no-recursive" "$MOCK_ARGS_FILE"
  grep -qx -- "--max-depth"    "$MOCK_ARGS_FILE"
  grep -qx -- "5"              "$MOCK_ARGS_FILE"
}

@test "IN_FILE is passed as the final positional argument" {
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  # Last line of args file should be the file path
  last="$(tail -n1 "$MOCK_ARGS_FILE")"
  [ "$last" = "$IN_FILE" ]
}

# ---------------------------------------------------------------------------
# output-file
# ---------------------------------------------------------------------------

@test "output-file without recursive — exits 1 with error message" {
  export IN_OUTPUT_FILE="$TEST_TEMP/out.txt"
  export IN_RECURSIVE="false"
  run bash "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"output-file requires recursive: true"* ]]
}

@test "output-file with recursive:true — --output passed" {
  export IN_OUTPUT_FILE="$TEST_TEMP/out.txt"
  export IN_RECURSIVE="true"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -qx -- "--output"        "$MOCK_ARGS_FILE"
  grep -qx -- "$IN_OUTPUT_FILE" "$MOCK_ARGS_FILE"
}

# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

@test "config as file path — STAC_CHECK_CONFIG set to that path" {
  CONFIG_FILE="$TEST_TEMP/stac.yml"
  echo "linting: {}" > "$CONFIG_FILE"
  export IN_CONFIG="$CONFIG_FILE"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "STAC_CHECK_CONFIG=$CONFIG_FILE" "$MOCK_ENV_FILE"
}

@test "config as inline YAML — temp file written, STAC_CHECK_CONFIG set" {
  export IN_CONFIG="$(printf 'linting:\n  check_geometry: false')"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "STAC_CHECK_CONFIG=" "$MOCK_ENV_FILE"
  CONFIG_PATH="$(grep "STAC_CHECK_CONFIG=" "$MOCK_ENV_FILE" | cut -d= -f2)"
  [ -f "$CONFIG_PATH" ]
  grep -q "check_geometry" "$CONFIG_PATH"
}

@test "config as single-line inline YAML — temp file written, STAC_CHECK_CONFIG set" {
  export IN_CONFIG="{linting: {check_geometry: false}}"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "STAC_CHECK_CONFIG=" "$MOCK_ENV_FILE"
  CONFIG_PATH="$(grep "STAC_CHECK_CONFIG=" "$MOCK_ENV_FILE" | cut -d= -f2)"
  [ -f "$CONFIG_PATH" ]
  grep -q "check_geometry" "$CONFIG_PATH"
}

@test "config that looks like a missing .yml path — exits 1" {
  export IN_CONFIG="does-not-exist.yml"
  run bash "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"not an existing file and does not look like inline YAML"* ]]
}

@test "config that looks like a missing path with slashes — exits 1" {
  export IN_CONFIG=".github/missing-config.yaml"
  run bash "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"not an existing file and does not look like inline YAML"* ]]
}

@test "config that's a bare typo with no extension or slash — exits 1" {
  export IN_CONFIG="config"
  run bash "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"not an existing file and does not look like inline YAML"* ]]
}

@test "log-path is set even on early exit (e.g. invalid output-file)" {
  export IN_OUTPUT_FILE="$TEST_TEMP/out.txt"
  export IN_RECURSIVE="false"
  run bash "$SCRIPT"
  [ "$status" -eq 1 ]
  grep -q "log-path=" "$GITHUB_OUTPUT"
}

@test "log-path is set even on early exit (e.g. invalid config)" {
  export IN_CONFIG="missing.yml"
  run bash "$SCRIPT"
  [ "$status" -eq 1 ]
  grep -q "log-path=" "$GITHUB_OUTPUT"
}

# ---------------------------------------------------------------------------
# valid parsing (output marker detection)
# ---------------------------------------------------------------------------

@test "valid=true when output is empty" {
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "valid=true" "$GITHUB_OUTPUT"
}

@test "valid=true when output looks healthy" {
  export MOCK_STDOUT="Item Passed: True
Recursive validation has passed!
Passed: 5/5"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "valid=true" "$GITHUB_OUTPUT"
}

@test "valid=false on 'Recursive validation has failed!'" {
  export MOCK_STDOUT="Recursive validation has failed!"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "valid=false" "$GITHUB_OUTPUT"
}

@test "valid=false on 'Failed: 3/10'" {
  export MOCK_STDOUT="Validation Summary
Passed: 7/10
Failed: 3/10"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "valid=false" "$GITHUB_OUTPUT"
}

@test "valid=true on 'Failed: 0/10' (zero failures)" {
  export MOCK_STDOUT="Validation Summary
Passed: 10/10
Failed: 0/10"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "valid=true" "$GITHUB_OUTPUT"
}

@test "valid=false on 'Item Passed: False'" {
  export MOCK_STDOUT="Item Passed: False"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "valid=false" "$GITHUB_OUTPUT"
}

@test "valid=false on 'Valid: False' (fallback display)" {
  export MOCK_STDOUT="Valid: False
Schemas checked: ..."
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "valid=false" "$GITHUB_OUTPUT"
}

@test "valid=false even when stac-check exit code is 0" {
  export MOCK_EXIT_CODE=0
  export MOCK_STDOUT="Recursive validation has failed!"
  run bash "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "exit-code=0" "$GITHUB_OUTPUT"
  grep -q "valid=false" "$GITHUB_OUTPUT"
}
