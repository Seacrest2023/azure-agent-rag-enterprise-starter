#!/usr/bin/env bash
# The Python checks, the same on your computer and in CI. The `python` job runs
# the default branch's copy of this script against the PR's code.
#   Here:  uv run bash scripts/check_python.sh
#   CI:    bash check_python.sh <base commit>
# Every check runs, and every failure is reported, not just the first.
set -uo pipefail
base=${1:-origin/main}
failed=()

check() {
  local name=$1 rc
  shift
  if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::group::$name"; else echo "== $name"; fi
  "$@"
  rc=$?
  if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::endgroup::"; fi
  [ "$rc" -eq 0 ] || failed+=("$name")
}

check "lint" ruff check --ignore-noqa .
check "format" ruff format --check .
check "types" basedpyright
check "tests" pytest --cov --cov-report=xml --cov-report=term
check "changed-line coverage" diff-cover coverage.xml --compare-branch="$base" --fail-under=80
check "dependencies" deptry src
check "dead code" vulture

audit=$(mktemp)
if uv export --frozen --no-emit-project --quiet > "$audit"; then
  check "known vulnerabilities" pip-audit -r "$audit" --require-hashes --disable-pip --progress-spinner off
else
  failed+=("known vulnerabilities (couldn't export the lockfile)")
fi
rm -f "$audit"

if [ ${#failed[@]} -gt 0 ]; then
  printf 'Failed: %s\n' "${failed[@]}" >&2
  exit 1
fi
echo "All Python checks passed."
