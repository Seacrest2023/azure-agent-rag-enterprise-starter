#!/usr/bin/env bash
# Automated checks for a pull request, run by .github/workflows/security-gate.yml
# from the default branch's copy of this script and its helpers. It reads PR
# content through the GitHub API and never executes it. tests/gate/ runs it
# against known-good and known-bad pull requests.
#
# Inputs (environment): REPO PR CHANGED_FILES COMMIT_COUNT BASE_SHA HEAD_SHA
#   HEAD_REPO PR_TITLE PR_BODY GITHUB_STEP_SUMMARY RUNNER_TEMP
# Optional (tests point these at fixtures): PATHS_FILE BLOCKED_TERMS_FILE
#   STACK_FILE TRUSTED_WORKFLOW PYTHON
# Needs: gh, jq, Python 3 with PyYAML, zizmor. Exit 0 = pass, 1 = fail. Any
# unexpected error also fails: the gate never passes on a partial view.

set -Eeuo pipefail  # -E: the ERR trap also fires inside functions
trap 'echo "::error::The gate hit an unexpected error at line $LINENO; refusing to pass." >&2' ERR  # stderr: stdout may be redirected

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PATHS_FILE=${PATHS_FILE:-.github/security-critical-paths.txt}
STACK_FILE=${STACK_FILE:-.claude/security-stack.json}
TRUSTED_WORKFLOW=${TRUSTED_WORKFLOW:-.github/workflows/security-gate.yml}
PYTHON=${PYTHON:-python3}
PR_TITLE=${PR_TITLE:-}
PR_BODY=${PR_BODY:-}
failed=0

say() { echo "$*"; echo "$*" >> "$GITHUB_STEP_SUMMARY"; }
fail() { echo "::error::$1"; say "### Failed: $1"; failed=1; }
refuse() { echo "::error::$1; refusing to pass." >&2; exit 1; }
bullets() { sed '/^$/d; s/^/- /' | tee -a "$GITHUB_STEP_SUMMARY"; }
# A file's contents at a commit. Each path segment is URL-encoded, so names
# with spaces, # or ? fetch the right file.
raw() {
  local path
  path=$(jq -rn --arg p "$2" '$p | split("/") | map(@uri) | join("/")')
  gh api -H "Accept: application/vnd.github.raw" "repos/$1/contents/$path?ref=$3"
}
# The Python helpers print one finding per line and exit 1 when they have any,
# 2 when they couldn't run. A helper that couldn't run stops the gate.
helper() {
  local rc=0
  "$PYTHON" "$here/$1" "${@:2}" || rc=$?
  [ "$rc" -le 1 ] || refuse "$1 could not run"
  return 0
}
terms() { helper check_blocked_terms.py "$@"; }

# Comment markers count only as comments, so prose that mentions one doesn't:
# zizmor reads YAML comments; detect-secrets reads #, //, /*, --, <!-- and ;.
# Python's lint, type-check and coverage silencers are # comments too. Test
# skips are code, so docs describe them in words. None of these patterns
# matches its own text, so this file can be edited without tripping the gate.
# Matching is line by line: a skip split across lines, or called through an
# alias, gets past these patterns.
python_markers='#[[:space:]]*((ruff|flake8):[[:space:]]*)?[Nn][Oo][Qq][Aa]|#[[:space:]]*type:[[:space:]]*ignore|#[[:space:]]*(pyright|mypy):|#[[:space:]]*(pragma|PRAGMA)(:|[[:space:]])*(no|NO)[[:space:]]*(cover|COVER|branch|BRANCH)'
skip_markers='mark\.(skip|skipif|xfail)|pytest\.(skip|xfail|importorskip)[[:space:]]*\(|unittest\.(skip|skipIf|skipUnless|expectedFailure)|@(skip|skipIf|skipUnless|expectedFailure)([^A-Za-z0-9_]|$)|skipTest[[:space:]]*\(|S[k]ipTest|from[[:space:]]+(pytest|unittest)[[:space:]]+import[[:space:]][^#]*(skip|xfail|expectedFailure)'
markers='#[[:space:]]*zizmor:[[:space:]]*ignore\[|(#|//|/\*|--|<!--|;).*pragma[:=][[:space:]]*allowlist[ -](nextline[ -])?secret'"|$python_markers|$skip_markers"
# The marker itself, for counting occurrences within lines that match $markers.
marker_core='zizmor:[[:space:]]*ignore\[|pragma[:=][[:space:]]*allowlist[ -](nextline[ -])?secret'"|$python_markers|$skip_markers"
count_markers() { { grep -aE "$markers" "$1" || true; } | { grep -aoE "$marker_core" || true; } | wc -l; }

# --- Trusted inputs (the default branch's copies) --------------------------------
patterns=$(mktemp)
grep -Ev '^\s*(#|$)' "$PATHS_FILE" > "$patterns" || true
[ -s "$patterns" ] || refuse "$PATHS_FILE has no patterns"
# grep exits 2 on an invalid expression; never let that read as "no match".
rc=0; grep -E -f "$patterns" < /dev/null > /dev/null || rc=$?
[ "$rc" -le 1 ] || refuse "$PATHS_FILE contains an invalid regular expression"
required=$(jq -r '.github.required_checks[]?' "$STACK_FILE")
[ -n "$required" ] || refuse "$STACK_FILE lists no required checks"

# --- The pull request, as the API reports it --------------------------------------
files=$(mktemp)
gh api --paginate "repos/$REPO/pulls/$PR/files" --jq '.[]' > "$files"
listed=$(jq -s length "$files")
[ "$listed" -eq "$CHANGED_FILES" ] || refuse "The API listed $listed of $CHANGED_FILES changed files (it stops at 3000)"
commits=$(mktemp)
gh api --paginate "repos/$REPO/pulls/$PR/commits" --jq '.[] | {sha, message: .commit.message}' > "$commits"
listed=$(jq -s length "$commits")
[ "$listed" -eq "$COMMIT_COUNT" ] || refuse "The API listed $listed of $COMMIT_COUNT commits (it stops at 250)"

status_of() { jq -r --arg f "$1" 'select(.filename == $f) | .status' "$files"; }
moved_or_deleted() {
  jq -e --arg f "$1" 'select((.filename == $f or .previous_filename == $f) and (.status == "removed" or .status == "renamed"))' "$files" > /dev/null
}
# The base copy of a changed file (under its old name if renamed): empty only
# when the PR adds the file; any other failure to fetch stops the gate.
base_copy() {
  local old
  [ "$(status_of "$1")" = "added" ] && return 0
  old=$(jq -r --arg f "$1" 'select(.filename == $f) | .previous_filename // empty' "$files")
  raw "$REPO" "${old:-$1}" "$BASE_SHA"
}
head_copy() { raw "$HEAD_REPO" "$1" "$HEAD_SHA"; }
head_tmp=$(mktemp)
base_tmp=$(mktemp)

# --- 1. No new suppressions, in any file ---------------------------------------
suppressions=$(jq -r --arg m "$markers" 'select(.patch != null) | .filename as $f | .patch | split("\n")[]
  | select(startswith("+") and test($m)) | "\($f): \(.[1:])"' "$files")
# GitHub omits the diff for large or binary files: compare marker counts instead,
# counting occurrences, not lines, so a second marker on an existing line is new.
while IFS= read -r f; do
  head_copy "$f" > "$head_tmp"   # fetched to files first, so a failed fetch stops the gate
  base_copy "$f" > "$base_tmp"
  head_n=$(count_markers "$head_tmp")
  base_n=$(count_markers "$base_tmp")
  if [ "$head_n" -gt "$base_n" ]; then
    suppressions="$suppressions"$'\n'"$f: $((head_n - base_n)) added (no diff available)"
  fi
done < <(jq -r 'select(.patch == null and .status != "removed") | .filename' "$files")
suppressions=$(printf '%s\n' "$suppressions" | sed '/^$/d')
if [ -n "$suppressions" ]; then
  fail "new check suppressions"
  printf '%s\n' "$suppressions" | bullets
  echo "Fix the finding instead of suppressing it."
fi

# --- 2. No blocked names, anywhere in the PR ------------------------------------
# The full content of every changed file (so a name split between old and new
# lines is caught), file paths, the PR title and description, and every commit
# message. Unchanged files were clean on the base branch.
hits=$(mktemp)
while IFS= read -r f; do
  head_copy "$f" > "$head_tmp"
  terms --stdin "$f" < "$head_tmp" >> "$hits"
done < <(jq -r 'select(.status != "removed") | .filename' "$files")
jq -r '.filename' "$files" | terms --stdin-paths "file path" >> "$hits"
printf '%s\n%s\n' "$PR_TITLE" "$PR_BODY" | terms --stdin "PR title/description" >> "$hits"
jq -r '.message' "$commits" | terms --stdin "commit messages" >> "$hits"
if [ -s "$hits" ]; then
  fail "blocked names (companies or other names this repository must not mention)"
  bullets < "$hits"
fi

# --- 3. Workflows: zizmor, and nothing that weakens the required checks ---------
if moved_or_deleted "$TRUSTED_WORKFLOW"; then
  fail "$TRUSTED_WORKFLOW is renamed or deleted; the required checks come from it"
fi
mapfile -t workflows < <(jq -r 'select(.status != "removed") | .filename | select(test("^\\.github/workflows/.+\\.ya?ml$"))' "$files")
if [ "${#workflows[@]}" -gt 0 ]; then
  pr_dir="$RUNNER_TEMP/pr"
  for f in "${workflows[@]}"; do
    mkdir -p "$pr_dir/$(dirname "$f")"
    head_copy "$f" > "$pr_dir/$f"
  done
  # Static analysis only, and without the token, so even a compromised scanner can't use it.
  if (cd "$pr_dir" && env -u GH_TOKEN zizmor --offline --format plain "${workflows[@]}"); then
    say "zizmor: no findings in changed workflows."
  else
    fail "zizmor findings in changed workflows"
  fi
  required_args=()
  while IFS= read -r name; do required_args+=(--required "$name"); done <<< "$required"
  findings=$(helper workflow_checks.py --root "$pr_dir" --trusted "$TRUSTED_WORKFLOW" "${required_args[@]}" "${workflows[@]}")
  if [ -n "$findings" ]; then
    fail "workflow changes that could weaken the required checks"
    printf '%s\n' "$findings" | bullets
  fi
fi

# --- 4. Protected lists may grow but never lose an entry, move or disappear -------
# Extractors print one line per protected entry. A parse failure stops the
# gate (the PR's copy must be valid), rather than reading as "no entries".
lines_of()      { grep -Ev '^\s*(#|$)' || true; }
precommit_of()  { "$PYTHON" "$here/precommit_hooks.py"; }   # hook definitions and global settings; rev may change
guard_of()      { jq -r '(if .disableAllHooks == true then empty else "hooks enabled" end),
                         ((.hooks // {}) | to_entries[] | .key as $e | .value[]
                           | .matcher as $m | .hooks[] | "\($e) \($m // "") \(.type) \(.command)")'; }
# VS Code reads an event's names without regard to case (PreToolUse is preToolUse), and one overwrites the
# other, so each event's set of names is an entry: adding an alias changes it. So are the top-level keys.
copilot_of()    { jq -r '"top-level keys: \(keys | join(","))",
                         (if .disableAllHooks == true then empty else "hooks enabled" end),
                         ((.hooks // {}) | keys | group_by(ascii_downcase)[] | "event \(.[0] | ascii_downcase): \(join(","))"),
                         ((.hooks // {}) | to_entries[] | .key as $e | .value[]
                           | "\($e) \(to_entries | sort_by(.key) | map("\(.key)=\(.value | if type == "object"
                               then (to_entries | sort_by(.key) | from_entries) else . end | tojson)") | join(" | "))")'; }
required_of()   { jq -r '.github.required_checks[]?'; }
deny_of()       { jq -r '(.permissions.deny // [])[]'; }
packages_of()   { { grep -oE '^[A-Za-z0-9][A-Za-z0-9_.-]*' || true; } | tr '[:upper:]' '[:lower:]' | tr '_.' '--'; }  # names as pip normalises them
test_names_of() { grep -oE '^\s*def test_[A-Za-z0-9_]+' | sed -E 's/.*def //' || true; }

protect() { # file, extractor, what the entries are
  local f=$1 extract=$2 what=$3 base head base_items="" head_items removed
  if moved_or_deleted "$f"; then
    fail "$f is renamed or deleted; the gate relies on it at this path"
    return
  fi
  [ -n "$(status_of "$f")" ] || return 0
  base=$(base_copy "$f")
  head=$(head_copy "$f")
  [ -z "$base" ] || base_items=$(printf '%s\n' "$base" | $extract | sort -u)
  head_items=$(printf '%s\n' "$head" | $extract | sort -u)
  removed=$(comm -23 <(printf '%s\n' "$base_items") <(printf '%s\n' "$head_items") | sed '/^$/d')
  if [ -n "$removed" ]; then
    fail "$what removed or changed in $f"
    printf '%s\n' "$removed" | bullets
  fi
}
protect "$PATHS_FILE"                         lines_of      "security-critical path patterns"
protect .github/blocked-terms.txt             lines_of      "blocked-name entries"
protect .pre-commit-config.yaml               precommit_of  "pre-commit hooks or settings"
protect .claude/settings.json                 guard_of      "agent hook registrations"
protect .claude/settings.json                 deny_of       "permission deny rules"
protect .github/hooks/agent-guard.json        copilot_of    "Copilot Chat hook registrations"
protect "$STACK_FILE"                         required_of   "required check names"
protect tests/gate/test_security_gate.py      test_names_of "gate test cases"
protect tests/hooks/test_block_hook_bypass.py test_names_of "hook-bypass guard test cases"
protect tests/gate/test_github_settings.py    test_names_of "GitHub settings check test cases"
protect tests/gate/test_secret_scan_step.py   test_names_of "secret-scan step test cases"
# Each hook repository is pinned by a full commit hash: a tag, branch or short hash is looked up by
# name, so its owner could point it at other code after it was reviewed.
if [ -n "$(status_of .pre-commit-config.yaml)" ] && ! moved_or_deleted .pre-commit-config.yaml; then
  head_copy .pre-commit-config.yaml > "$head_tmp"   # fetched to a file first, so a failed fetch stops the gate
  unpinned=$(helper precommit_hooks.py --pins < "$head_tmp")
  if [ -n "$unpinned" ]; then
    fail "pre-commit hook pinned to something other than a full commit hash"
    printf '%s\n' "$unpinned" | sed 's/\t/ at rev /' | bullets
  fi
fi
# Pinned tools run inside the trusted jobs, so their lists are frozen apart from
# versions and hashes: no package added, removed or swapped (adding one needs
# the owner), and no list added, renamed or deleted.
while IFS= read -r f; do
  if moved_or_deleted "$f"; then
    fail "$f is renamed or deleted; the trusted jobs install from it"
    continue
  fi
  base=$(base_copy "$f")
  head=$(head_copy "$f")
  base_items=$(printf '%s\n' "$base" | packages_of | sort -u)
  head_items=$(printf '%s\n' "$head" | packages_of | sort -u)
  changed=$( { comm -23 <(printf '%s\n' "$base_items") <(printf '%s\n' "$head_items") | sed 's/^/removed: /'
               comm -13 <(printf '%s\n' "$base_items") <(printf '%s\n' "$head_items") | sed 's/^/added: /'; } \
             | grep -Ev '^(removed|added): $' || true)
  if [ -n "$changed" ]; then
    fail "pinned tool packages changed in $f (only versions and hashes may change)"
    printf '%s\n' "$changed" | bullets
  fi
done < <(jq -r '.filename, (.previous_filename // empty)' "$files" | grep -E '^\.github/requirements/[^/]+\.txt$' | sort -u || true)

# --- 5. Secret scanning may get stricter, never looser -----------------------------
if moved_or_deleted .secrets.baseline; then
  fail ".secrets.baseline is renamed or deleted; secret scanning relies on it"
elif [ -n "$(status_of .secrets.baseline)" ]; then
  # Both copies are fetched to files first, so a failed fetch stops the gate.
  base_copy .secrets.baseline > "$base_tmp"
  head_copy .secrets.baseline > "$head_tmp"
  findings=$(helper baseline_checks.py "$base_tmp" "$head_tmp")
  if [ -n "$findings" ]; then
    fail "secret scanning loosened in .secrets.baseline"
    printf '%s\n' "$findings" | bullets
    echo "Remove the secret, or restructure the content, instead of loosening the scan."
  fi
fi

# --- 6. Security-critical paths, and areas whose tests arrive with later phases ------
rc=0
matched=$(jq -r '.filename, (.previous_filename // empty)' "$files" | grep -E -f "$patterns" | sort -u) || rc=$?
[ "$rc" -le 1 ] || refuse "Matching changed files against $PATHS_FILE failed"
if [ -z "$matched" ]; then
  say "No security-critical paths changed."
else
  say "### Security-critical paths changed"
  printf '%s\n' "$matched" | bullets
  covered='^\.github/(workflows|requirements)/|^\.secrets\.baseline$|^\.github/(security-critical-paths|blocked-terms)\.txt$|^\.pre-commit-config\.yaml$|^\.claude/(settings|security-stack)\.json$|^(scripts|tests)/'
  pending=$(printf '%s\n' "$matched" | grep -Ev "$covered" || true)
  if [ -n "$pending" ]; then
    say "### Changed without a dedicated automated check yet"
    printf '%s\n' "$pending" | bullets
  fi
fi

exit $failed
