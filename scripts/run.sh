#!/usr/bin/env bash
# Run stac-check with inputs supplied via environment variables.
# Called by action.yml; testable standalone with a mock stac-check on PATH.
#
# Required env vars (set by action.yml env: block):
#   IN_FILE, IN_RECURSIVE, IN_MAX_DEPTH, IN_VALIDATE_ASSETS, IN_PYDANTIC,
#   IN_VERBOSE, IN_FAST, IN_FAST_LINTING, IN_OUTPUT_FILE, IN_EXTRA_ARGS,
#   IN_CONFIG, IN_STREAM_OUTPUT
#
# GitHub Actions env vars (defaulted for local/test use):
#   GITHUB_OUTPUT, RUNNER_TEMP
set -euo pipefail

: "${GITHUB_OUTPUT:=/dev/null}"
: "${RUNNER_TEMP:=$(mktemp -d)}"

# Create log file FIRST so log-path output is set even on early exits.
OUTPUT_PATH="$(mktemp "$RUNNER_TEMP/stac-check-output.XXXXXX.txt")"
echo "log-path=$OUTPUT_PATH" >> "$GITHUB_OUTPUT"

ARGS=()

if [ "${IN_RECURSIVE:-false}" = "true" ]; then
  ARGS+=(--recursive)
  if [ -n "${IN_MAX_DEPTH:-}" ]; then
    ARGS+=(--max-depth "$IN_MAX_DEPTH")
  fi
fi

if [ "${IN_VALIDATE_ASSETS:-false}" = "true" ]; then
  ARGS+=(--assets --no-assets-urls)
fi

[ "${IN_PYDANTIC:-false}"      = "true" ] && ARGS+=(--pydantic)
[ "${IN_VERBOSE:-false}"       = "true" ] && ARGS+=(--verbose)

if [ "${IN_FAST:-false}" = "true" ]; then
  ARGS+=(--fast)
elif [ "${IN_FAST_LINTING:-false}" = "true" ]; then
  ARGS+=(--fast-linting)
fi

if [ -n "${IN_OUTPUT_FILE:-}" ]; then
  if [ "${IN_RECURSIVE:-false}" != "true" ]; then
    echo "::error::output-file requires recursive: true (stac-check CLI limitation)"
    exit 1
  fi
  ARGS+=(--output "$IN_OUTPUT_FILE")
fi

# Append extra-args (word-split intentionally for CLI flags)
if [ -n "${IN_EXTRA_ARGS:-}" ]; then
  # shellcheck disable=SC2206
  EXTRA=($IN_EXTRA_ARGS)
  ARGS+=("${EXTRA[@]}")
fi

ARGS+=("${IN_FILE:?IN_FILE is required}")

# Handle config: existing file path OR inline YAML.
# Heuristic: anything without a YAML structural marker (':' or newline) cannot
# be valid YAML, so we treat it as a (likely typo'd) file path and require it
# to exist. Multi-line or ':'-containing values are written to a temp file.
if [ -n "${IN_CONFIG:-}" ]; then
  if [ -f "$IN_CONFIG" ]; then
    export STAC_CHECK_CONFIG="$IN_CONFIG"
  elif [[ "$IN_CONFIG" != *:* && "$IN_CONFIG" != *$'\n'* ]]; then
    echo "::error::config input is not an existing file and does not look like inline YAML (no ':' or newline): $IN_CONFIG"
    exit 1
  else
    CONFIG_PATH="$(mktemp "$RUNNER_TEMP/stac-check-config.XXXXXX.yml")"
    printf '%s' "$IN_CONFIG" > "$CONFIG_PATH"
    export STAC_CHECK_CONFIG="$CONFIG_PATH"
  fi
fi

# Stream through tee so per-item progress (stac-check prints a line as each
# object validates) shows up in the Actions log live instead of only
# appearing once the whole run finishes. Toggleable via stream-output input
# for callers who'd rather keep the log quiet until the summary at the end.
#
# PYTHONUNBUFFERED is required here: stac-check is a Python CLI, and Python
# fully buffers stdout (rather than line-buffering) whenever it isn't a TTY,
# which a pipe to tee never is. Without it, tee gets nothing to stream until
# Python's internal buffer fills or the process exits, defeating the point.
set +e
if [ "${IN_STREAM_OUTPUT:-true}" = "true" ]; then
  PYTHONUNBUFFERED=1 stac-check "${ARGS[@]}" 2>&1 | tee "$OUTPUT_PATH"
  EXIT_CODE="${PIPESTATUS[0]}"
else
  stac-check "${ARGS[@]}" > "$OUTPUT_PATH" 2>&1
  EXIT_CODE=$?
  cat "$OUTPUT_PATH"
fi
set -e

echo "exit-code=$EXIT_CODE" >> "$GITHUB_OUTPUT"

# Parse output for explicit failure markers. stac-check's exit code is
# unreliable in recursive mode (often returns 0 even with failures), so we
# scan for known failure indicators emitted by display_messages.py.
#
# Markers (any one => valid=false):
#   - "Recursive validation has failed!"   recursive-mode summary banner
#   - "Failed: N/M" where N >= 1           summary fail count (fast + standard)
#   - "Passed: False"                      single-item validation status
#   - "Valid: False"                       fallback display
#
# Also treat any non-zero CLI exit as invalid so hard errors that do not
# print one of the markers cannot be misreported as valid.
VALID="true"
if grep -qE 'Recursive validation has failed!|Failed: [1-9][0-9]*/|Passed: False|Valid: False' "$OUTPUT_PATH"; then
  VALID="false"
elif [ "$EXIT_CODE" -ne 0 ]; then
  VALID="false"
fi
echo "valid=$VALID" >> "$GITHUB_OUTPUT"
