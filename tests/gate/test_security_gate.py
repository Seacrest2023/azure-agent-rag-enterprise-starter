"""Tests for scripts/security_gate.sh, run against a fake GitHub API.

Each case describes a pull request (changed files, base and head contents,
commit messages, title, description) and asserts the gate passes or fails
with the expected reason. The security gate refuses PRs that delete test
cases here, and CI runs the default branch's copy of these tests against a
PR's code, so weakening the gate's logic fails these tests instead of passing
quietly.

Run: python -m unittest discover -s tests/gate -t .
Needs bash, jq, PyYAML and zizmor (CI installs them from
.github/requirements/gate-tools.txt; locally the cases that need zizmor are
skipped without it unless REQUIRE_ZIZMOR=1).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

# SECURITY_CODE_ROOT points these tests at another copy of the code: CI runs the
# default branch's tests against the PR's scripts, so a PR can't weaken the
# gate and its tests together.
ROOT = os.path.abspath(os.environ.get("SECURITY_CODE_ROOT") or os.path.join(os.path.dirname(__file__), "..", ".."))
GATE = os.path.join(ROOT, "scripts", "security_gate.sh")
PATHS = ".github/security-critical-paths.txt"
STACK = ".claude/security-stack.json"
TRUSTED = ".github/workflows/security-gate.yml"
BASH = shutil.which("bash")
REAL_JQ = shutil.which("jq")
HAVE_ZIZMOR = bool(shutil.which("zizmor") or os.environ.get("REQUIRE_ZIZMOR"))

FAKE_GH = r'''
import json, os, sys, urllib.parse
case = os.environ["FAKE_GH_CASE"]
args = sys.argv[1:]
assert args and args[0] == "api", args
path, i = None, 1
while i < len(args):
    if args[i] in ("-H", "--jq", "-X", "-f", "-F"):
        i += 2
        continue
    if not args[i].startswith("-") and path is None:
        path = args[i]
    i += 1
if path.endswith("/files"):
    for f in json.load(open(os.path.join(case, "files.json"))):
        print(json.dumps(f))
elif path.endswith("/commits"):
    for n, message in enumerate(json.load(open(os.path.join(case, "commits.json")))):
        print(json.dumps({"sha": "c%d" % n, "message": message}))
elif "/contents/" in path:
    rel, ref = path.split("/contents/", 1)[1].split("?ref=")
    side = "head" if ref == "HEADSHA" else "base"
    p = os.path.join(case, side, urllib.parse.unquote(rel))
    if not os.path.isfile(p):
        sys.stderr.write("gh: Not Found (HTTP 404)\n")
        sys.exit(1)
    sys.stdout.buffer.write(open(p, "rb").read())
else:
    sys.stderr.write("fake gh: unhandled " + path + "\n")
    sys.exit(1)
'''

# Suppression markers are assembled from parts so this file never contains one:
# the gate (rightly) fails any PR that adds a real marker.
PRAGMA = "# pragma: " + "allowlist secret"
ZIZMOR_IGNORE = "# zizmor: " + "ignore[x]"


def patch(*lines):
    return f"@@ -0,0 +1,{len(lines)} @@\n" + "\n".join("+" + line for line in lines)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def workflow(jobs, on="pull_request"):
    return f"name: t\non: {on}\npermissions: {{}}\njobs:\n{jobs}"


class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        bin_dir = os.path.join(self.tmp, "bin")
        os.makedirs(bin_dir)
        with open(os.path.join(bin_dir, "fake_gh.py"), "w") as fh:
            fh.write(FAKE_GH)
        self._script(bin_dir, "gh", f'exec "{sys.executable}" "$(dirname "$0")/fake_gh.py" "$@"')
        if os.name == "nt":  # jq on Windows writes CRLF; the gate runs on Linux in CI
            self._script(bin_dir, "jq", f'set -o pipefail; "{REAL_JQ}" "$@" | tr -d "\\r"')
        self.bin_dir = bin_dir
        terms = os.path.join(self.tmp, "terms.txt")
        script = os.path.join(ROOT, "scripts", "check_blocked_terms.py")
        for args in (["--add", "ZebraCorp"], ["--add", "--paths", "quokka"]):
            subprocess.run([sys.executable, script, *args], env={**os.environ, "BLOCKED_TERMS_FILE": terms},
                           check=True, capture_output=True)
        self.terms = terms

    @staticmethod
    def _script(bin_dir, name, body):
        path = os.path.join(bin_dir, name)
        with open(path, "w", newline="\n") as fh:
            fh.write("#!/usr/bin/env bash\n" + body + "\n")
        os.chmod(path, 0o755)

    def gate(self, files, head=None, base=None, commits=("add feature",), title="Add feature", body="",
             changed_files=None, commit_count=None, paths_file=PATHS, terms_file=None):
        case = os.path.join(self.tmp, "case")
        head = dict(head or {})
        for f in files:  # a changed file's head copy defaults to its patch's added lines
            if f.get("status") != "removed" and f["filename"] not in head and f.get("patch"):
                head[f["filename"]] = "\n".join(l[1:] for l in f["patch"].split("\n") if l.startswith("+")) + "\n"
        for side, contents in (("head", head), ("base", base or {})):
            for rel, content in contents.items():
                p = os.path.join(case, side, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as fh:
                    fh.write(content if isinstance(content, bytes) else content.encode("utf-8"))
        os.makedirs(case, exist_ok=True)
        commits = [commits] if isinstance(commits, str) else list(commits)
        with open(os.path.join(case, "files.json"), "w") as fh:
            json.dump(files, fh)
        with open(os.path.join(case, "commits.json"), "w") as fh:
            json.dump(commits, fh)
        env = {
            **os.environ,
            "PATH": self.bin_dir + os.pathsep + os.environ["PATH"],
            "FAKE_GH_CASE": case, "PYTHON": sys.executable,
            "REPO": "owner/repo", "HEAD_REPO": "owner/repo", "PR": "1",
            "BASE_SHA": "BASESHA", "HEAD_SHA": "HEADSHA",
            "CHANGED_FILES": str(len(files) if changed_files is None else changed_files),
            "COMMIT_COUNT": str(len(commits) if commit_count is None else commit_count),
            "PR_TITLE": title, "PR_BODY": body,
            "GITHUB_STEP_SUMMARY": os.path.join(self.tmp, "summary.md"), "RUNNER_TEMP": self.tmp,
            "PATHS_FILE": paths_file, "BLOCKED_TERMS_FILE": terms_file or self.terms,
        }
        env.pop("GH_TOKEN", None)
        result = subprocess.run([BASH, GATE], cwd=ROOT, env=env, capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr

    def assertPasses(self, *args, **kwargs):
        code, out = self.gate(*args, **kwargs)
        self.assertEqual(code, 0, out)

    def assertFails(self, reason, *args, **kwargs):
        code, out = self.gate(*args, **kwargs)
        self.assertNotEqual(code, 0, out)
        self.assertIn(reason, out)

    def modified(self, path, head, base=None):
        """A PR modifying `path`: (files, head/base contents) for gate()."""
        return ([{"filename": path, "status": "modified", "patch": patch("x")}],
                {"head": {path: head}, "base": {path: read(path) if base is None else base}})

    # --- passes -------------------------------------------------------------
    def test_ungated_change_passes(self):
        self.assertPasses([{"filename": "src/app.py", "status": "added", "patch": patch("print('hi')")}])

    def test_clean_gated_change_passes(self):
        self.assertPasses([{"filename": "db/security/rls.sql", "status": "added", "patch": patch("-- policy")}])

    def test_prose_mentioning_markers_passes(self):
        self.assertPasses([{"filename": "docs/x.md", "status": "added",
                            "patch": patch("Never add a zizmor: ignore[...] or pragma: allowlist secret comment.")}])

    def test_path_only_name_allowed_in_content(self):
        self.assertPasses([{"filename": "docs/x.md", "status": "added", "patch": patch("a quokka appears")}])

    def test_allowlist_shrink_passes(self):
        base = json.dumps({"results": {"a.py": [{"type": "Secret Keyword", "hashed_secret": "1"}]}})
        head = json.dumps({"results": {}})
        self.assertPasses([{"filename": ".secrets.baseline", "status": "modified", "patch": patch("x")}],
                          head={".secrets.baseline": head}, base={".secrets.baseline": base})

    def test_path_pattern_added_passes(self):
        current = read(PATHS)
        self.assertPasses([{"filename": PATHS, "status": "modified", "patch": patch("^new/")}],
                          head={PATHS: current + "^new/\n"}, base={PATHS: current})

    def test_binary_file_passes(self):
        self.assertPasses([{"filename": "docs/img.png", "status": "added"}],
                          head={"docs/img.png": b"\x89PNG\r\n\x1a\n\x00\xff\xfe binary"})

    def test_file_name_with_space_and_hash_passes(self):
        # Space, # and % each break an unencoded contents URL. (? would too, but Windows can't create the fixture.)
        self.assertPasses([{"filename": "docs/a b#c%20d.md", "status": "added", "patch": patch("fine")}])

    # --- suppressions ---------------------------------------------------------
    def test_added_suppression_fails(self):
        self.assertFails("new check suppressions",
                         [{"filename": "src/app.py", "status": "added", "patch": patch("k = 'v'  " + PRAGMA)}])

    def test_added_zizmor_ignore_fails(self):
        self.assertFails("new check suppressions",
                         [{"filename": "src/w.yml", "status": "added", "patch": patch("on: push  " + ZIZMOR_IGNORE)}])

    def test_second_marker_on_same_line_without_diff_fails(self):
        line = "x = 1  " + PRAGMA
        self.assertFails("new check suppressions", [{"filename": "big.txt", "status": "modified"}],
                         head={"big.txt": line + "  " + PRAGMA + "\n"}, base={"big.txt": line + "\n"})

    def test_suppression_in_file_without_diff_fails(self):
        self.assertFails("new check suppressions", [{"filename": "big.txt", "status": "modified"}],
                         head={"big.txt": "a\nb  " + PRAGMA + "\n"}, base={"big.txt": "a\n"})

    def suppression_fails(self, line, filename="src/app.py"):
        # One gate run per form, so a pattern that stops matching one can't hide behind another.
        self.assertFails("new check suppressions", [{"filename": filename, "status": "added", "patch": patch(line)}])

    def test_added_noqa_fails(self):
        self.suppression_fails("import os  # no" + "qa: F401")
        self.suppression_fails("# ruff: no" + "qa")

    def test_added_type_ignore_fails(self):
        self.suppression_fails("x: int = f()  # type: " + "ignore[assignment]")
        self.suppression_fails("# pyr" + "ight: basic")
        self.suppression_fails("# my" + "py: ignore-errors")

    def test_added_no_cover_fails(self):
        self.suppression_fails("def main():  # pragma: " + "no cover")

    def test_added_pytest_skip_fails(self):
        self.suppression_fails("@pytest.mark." + "xfail(reason='flaky')", "tests/unit/test_x.py")
        self.suppression_fails("    pytest." + "skip('later')", "tests/unit/test_x.py")

    def test_added_unittest_skip_fails(self):
        self.suppression_fails("@unittest." + "skipIf(True, 'later')", "tests/unit/test_x.py")
        self.suppression_fails("@expected" + "Failure", "tests/unit/test_x.py")
        self.suppression_fails("        self.skip" + "Test('later')", "tests/unit/test_x.py")
        self.suppression_fails("    raise unittest.Skip" + "Test('later')", "tests/unit/test_x.py")

    def test_added_skip_import_fails(self):
        # Imported by name, the call itself is a bare skip(...) that no other pattern catches.
        self.suppression_fails("from py" + "test import skip", "tests/unit/test_x.py")
        self.suppression_fails("from py" + "test import mark, importorskip", "tests/unit/test_x.py")
        self.suppression_fails("from unit" + "test import skipIf", "tests/unit/test_x.py")

    def test_code_named_like_a_skip_passes(self):
        self.assertPasses([{"filename": "src/app.py", "status": "added",
                            "patch": patch("def skip(rows):", "    return rows.skip(2)", "skipped = 0  # type of row")}])
        self.assertPasses([{"filename": "tests/unit/test_x.py", "status": "added", "patch": patch("from pytest import fixture")}])

    def test_prose_about_python_suppressions_passes(self):
        self.assertPasses([{"filename": "docs/x.md", "status": "added",
                            "patch": patch("Don't add noqa, type-ignore or no-cover comments, and don't skip or xfail a test.")}])

    # --- blocked names ----------------------------------------------------------
    def test_blocked_name_in_added_line_fails(self):
        self.assertFails("blocked names", [{"filename": "docs/x.md", "status": "added", "patch": patch("We use Zebra-Corp")}])

    def test_blocked_name_in_file_without_diff_fails(self):
        self.assertFails("blocked names", [{"filename": "big.txt", "status": "added"}], head={"big.txt": "zebracorp\n"})

    def test_blocked_name_in_title_fails(self):
        self.assertFails("blocked names", [{"filename": "src/app.py", "status": "added", "patch": patch("x")}],
                         title="Port ZebraCorp gate")

    def test_blocked_name_in_description_fails(self):
        self.assertFails("blocked names", [{"filename": "src/app.py", "status": "added", "patch": patch("x")}],
                         body="Copied from zebracorp")

    def test_blocked_name_in_commit_message_fails(self):
        self.assertFails("blocked names", [{"filename": "src/app.py", "status": "added", "patch": patch("x")}],
                         commits=["add feature", "fix\n\nlike ZEBRACORP does"])

    def test_blocked_name_in_path_fails(self):
        self.assertFails("blocked names", [{"filename": "docs/quokka-notes.md", "status": "added", "patch": patch("x")}])

    def test_blocked_name_in_unchanged_line_of_modified_file_fails(self):
        self.assertFails("blocked names", [{"filename": "docs/x.md", "status": "modified", "patch": patch("new line")}],
                         head={"docs/x.md": "old ZebraCorp line\nnew line\n"}, base={"docs/x.md": "old ZebraCorp line\n"})

    def test_blocked_name_split_across_lines_fails(self):
        self.assertFails("blocked names", [{"filename": "docs/x.md", "status": "added", "patch": patch("We use Zebra", "Corp")}])

    # --- protected lists ------------------------------------------------------------
    def test_path_pattern_removed_fails(self):
        current = read(PATHS)
        head = "\n".join(l for l in current.splitlines() if l != "^infra/") + "\n"
        self.assertFails("security-critical path patterns removed",
                         [{"filename": PATHS, "status": "modified", "patch": patch("x")}],
                         head={PATHS: head}, base={PATHS: current})

    def test_path_list_renamed_fails(self):
        self.assertFails("renamed or deleted",
                         [{"filename": "docs/paths.txt", "previous_filename": PATHS, "status": "renamed"}],
                         head={"docs/paths.txt": read(PATHS)}, base={PATHS: read(PATHS)})

    def test_blocked_terms_entry_removed_fails(self):
        self.assertFails("blocked-name entries removed",
                         [{"filename": ".github/blocked-terms.txt", "status": "modified", "patch": patch("x")}],
                         head={".github/blocked-terms.txt": "5 aaa\n"},
                         base={".github/blocked-terms.txt": "5 aaa\n6 bbb\n"})

    PRECOMMIT = ("repos:\n  - repo: https://example.com/hooks\n    rev: " + "a" * 40 + "\n    hooks:\n"
                 "      - id: detect-secrets\n        args: [--baseline, .secrets.baseline]\n      - id: check-yaml\n")

    def precommit_case(self, head):
        return self.modified(".pre-commit-config.yaml", head, base=self.PRECOMMIT)

    def test_precommit_hook_removed_fails(self):
        files, sides = self.precommit_case(self.PRECOMMIT.replace("      - id: check-yaml\n", ""))
        self.assertFails("pre-commit hooks or settings removed or changed", files, **sides)

    def test_precommit_hook_narrowed_fails(self):
        files, sides = self.precommit_case(self.PRECOMMIT.replace(
            "      - id: check-yaml\n", "      - id: check-yaml\n        stages: [manual]\n"))
        self.assertFails("pre-commit hooks or settings removed or changed", files, **sides)

    def test_precommit_hook_args_changed_fails(self):
        files, sides = self.precommit_case(self.PRECOMMIT.replace("[--baseline, .secrets.baseline]", "[--version]"))
        self.assertFails("pre-commit hooks or settings removed or changed", files, **sides)

    def test_precommit_global_exclude_added_fails(self):
        files, sides = self.precommit_case("exclude: '.*'\n" + self.PRECOMMIT)
        self.assertFails("pre-commit hooks or settings removed or changed", files, **sides)

    def test_precommit_install_types_narrowed_fails(self):
        files, sides = self.precommit_case("default_install_hook_types: [commit-msg]\n" + self.PRECOMMIT)
        self.assertFails("pre-commit hooks or settings removed or changed", files, **sides)

    def test_precommit_invalid_config_fails_closed(self):
        files, sides = self.precommit_case("repos: [unclosed\n")
        self.assertFails("unexpected error", files, **sides)

    def test_precommit_rev_bump_passes(self):
        files, sides = self.precommit_case(self.PRECOMMIT.replace("a" * 40, "b" * 40))
        self.assertPasses(files, **sides)

    def test_precommit_hook_added_passes(self):
        files, sides = self.precommit_case(self.PRECOMMIT + "      - id: check-merge-conflict\n")
        self.assertPasses(files, **sides)

    def test_precommit_fail_fast_passes(self):
        files, sides = self.precommit_case("fail_fast: true\n" + self.PRECOMMIT)
        self.assertPasses(files, **sides)

    def test_precommit_local_and_meta_hooks_without_rev_pass(self):
        files, sides = self.precommit_case(self.PRECOMMIT + (
            "  - repo: local\n    hooks:\n      - id: x\n        name: x\n        entry: x\n        language: system\n"
            "  - repo: meta\n    hooks:\n      - id: check-hooks-apply\n"))
        self.assertPasses(files, **sides)

    def test_precommit_hook_pinned_by_name_fails(self):
        f, pin = ".pre-commit-config.yaml", "a" * 40
        for rev in ("a" * 12, "v5.0.0", "main", "A" * 40):
            with self.subTest(rev=rev):
                files, sides = self.precommit_case(self.PRECOMMIT.replace(pin, rev))
                self.assertFails("pre-commit hook pinned to something other than a full commit hash", files, **sides)
        with self.subTest("no rev"):
            files, sides = self.precommit_case(self.PRECOMMIT.replace(f"    rev: {pin}\n", ""))
            self.assertFails("pre-commit hook pinned to something other than a full commit hash", files, **sides)
        with self.subTest("a new config"):
            self.assertFails("pre-commit hook pinned to something other than a full commit hash",
                             [{"filename": f, "status": "added", "patch": patch("x")}],
                             head={f: self.PRECOMMIT.replace(pin, "v5.0.0")})

    def test_precommit_new_config_invalid_yaml_fails_closed(self):
        f = ".pre-commit-config.yaml"
        self.assertFails("unexpected error", [{"filename": f, "status": "added", "patch": patch("x")}],
                         head={f: "repos: [unclosed\n"})

    def settings_case(self, head):
        return self.modified(".claude/settings.json", head)

    def test_bypass_guard_removed_fails(self):
        files, sides = self.settings_case("{}")
        self.assertFails("agent hook registrations removed or changed", files, **sides)

    def test_bypass_guard_command_replaced_fails(self):
        settings = json.loads(read(".claude/settings.json"))
        settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = "true"
        settings["note"] = "block_hook_bypass.py"  # the old name kept elsewhere
        files, sides = self.settings_case(json.dumps(settings))
        self.assertFails("agent hook registrations removed or changed", files, **sides)

    def test_bypass_guard_matcher_narrowed_fails(self):
        settings = json.loads(read(".claude/settings.json"))
        settings["hooks"]["PreToolUse"][0]["matcher"] = "Write"
        files, sides = self.settings_case(json.dumps(settings))
        self.assertFails("agent hook registrations removed or changed", files, **sides)

    def test_all_hooks_disabled_fails(self):
        settings = json.loads(read(".claude/settings.json"))
        settings["disableAllHooks"] = True
        files, sides = self.settings_case(json.dumps(settings))
        self.assertFails("agent hook registrations removed or changed", files, **sides)

    def test_permission_deny_rule_removed_fails(self):
        settings = json.loads(read(".claude/settings.json"))
        settings["permissions"]["deny"] = settings["permissions"]["deny"][1:]
        files, sides = self.settings_case(json.dumps(settings))
        self.assertFails("permission deny rules removed or changed", files, **sides)

    def test_permission_deny_rule_added_passes(self):
        settings = json.loads(read(".claude/settings.json"))
        settings["permissions"]["deny"].append("Read(~/.kube/**)")
        files, sides = self.settings_case(json.dumps(settings))
        self.assertPasses(files, **sides)

    def test_session_start_hook_removed_fails(self):
        settings = json.loads(read(".claude/settings.json"))
        del settings["hooks"]["SessionStart"]
        files, sides = self.settings_case(json.dumps(settings))
        self.assertFails("agent hook registrations removed or changed", files, **sides)

    def test_agent_hook_added_passes(self):
        settings = json.loads(read(".claude/settings.json"))
        settings["hooks"]["PostToolUse"] = [{"matcher": "Edit", "hooks": [{"type": "command", "command": "echo ok"}]}]
        files, sides = self.settings_case(json.dumps(settings))
        self.assertPasses(files, **sides)

    def test_required_check_name_removed_fails(self):
        stack = json.loads(read(STACK))
        stack["github"]["required_checks"] = [c for c in stack["github"]["required_checks"] if c != "selftest"]
        files, sides = self.modified(STACK, json.dumps(stack))
        self.assertFails("required check names removed or changed", files, **sides)

    def test_stack_status_change_passes(self):
        stack = json.loads(read(STACK))
        stack["status"] = {"done_and_verified": ["everything"]}
        files, sides = self.modified(STACK, json.dumps(stack))
        self.assertPasses(files, **sides)

    PINNED = ("zizmor==1.30.1 --hash=sha256:" + "a" * 64 + "\n"
              "pyyaml==6.0.3 --hash=sha256:" + "b" * 64 + "\n")

    def test_pinned_package_swapped_fails(self):
        files, sides = self.modified(".github/requirements/gate-tools.txt",
                                     self.PINNED.replace("zizmor==", "zizm0r=="), base=self.PINNED)
        self.assertFails("pinned tool packages changed", files, **sides)

    def test_pinned_package_added_fails(self):
        files, sides = self.modified(".github/requirements/gate-tools.txt",
                                     self.PINNED + "extra==1.0 --hash=sha256:" + "d" * 64 + "\n", base=self.PINNED)
        self.assertFails("added: extra", files, **sides)

    def test_pinned_package_version_bump_passes(self):
        files, sides = self.modified(".github/requirements/gate-tools.txt",
                                     self.PINNED.replace("1.30.1", "1.31.0").replace("a" * 64, "c" * 64), base=self.PINNED)
        self.assertPasses(files, **sides)

    def test_gate_test_case_removed_fails(self):
        f = "tests/gate/test_security_gate.py"
        self.assertFails("gate test cases removed", [{"filename": f, "status": "modified", "patch": patch("x")}],
                         head={f: "    def test_a(self):\n"}, base={f: "    def test_a(self):\n    def test_b(self):\n"})

    def test_copilot_guard_removed_or_changed_fails(self):
        f = ".github/hooks/agent-guard.json"
        for change in ({"hooks": {}}, {"disableAllHooks": True}, {"windows": "exit 0"}, {"linux": "exit 0"},
                       {"osx": "true"}, {"cwd": "docs"}, {"timeout": 1}, {"env": {"PATH": "tools"}},
                       {"bash": "exit 0"}, {"version": 1}):
            hook = json.loads(read(f))
            if set(change) & {"hooks", "disableAllHooks", "version"}:
                hook.update(change)
            else:
                hook["hooks"]["PreToolUse"][0].update(change)
            files, sides = self.modified(f, json.dumps(hook))
            with self.subTest(change=change):
                self.assertFails("Copilot Chat hook registrations removed or changed", files, **sides)
        hook = json.loads(read(f))
        hook["hooks"]["preToolUse"] = [{"type": "command", "command": "exit 0"}]  # VS Code reads it as PreToolUse
        files, sides = self.modified(f, json.dumps(hook))
        with self.subTest("an event alias added"):
            self.assertFails("Copilot Chat hook registrations removed or changed", files, **sides)
        self.assertFails("renamed or deleted", [{"filename": f, "status": "removed"}])

    def test_copilot_hook_added_passes(self):
        f = ".github/hooks/agent-guard.json"
        hook = json.loads(read(f))
        hook["hooks"]["PostToolUse"] = [{"type": "command", "command": "echo ok"}]
        files, sides = self.modified(f, json.dumps(hook))
        self.assertPasses(files, **sides)
        self.assertPasses([{"filename": f, "status": "added", "patch": patch("x")}], head={f: read(f)})

    def test_other_tooling_test_case_removed_fails(self):
        for f, what in [("tests/gate/test_github_settings.py", "GitHub settings check test cases"),
                        ("tests/gate/test_secret_scan_step.py", "secret-scan step test cases")]:
            with self.subTest(f):
                self.assertFails(f"{what} removed", [{"filename": f, "status": "modified", "patch": patch("x")}],
                                 head={f: "    def test_a(self):\n"},
                                 base={f: "    def test_a(self):\n    def test_b(self):\n"})

    # --- the secret-scan baseline -------------------------------------------------------
    def baseline_case(self, base, head):
        return self.modified(".secrets.baseline", json.dumps(head), base=json.dumps(base))

    DETECTORS = [{"name": "AWSKeyDetector"}, {"name": "HexHighEntropyString", "limit": 3.0}]
    LINE_FILTER = {"path": "detect_secrets.filters.regex.should_exclude_line", "pattern": ["^rev: x$"]}

    def test_allowlist_swap_fails(self):
        base = json.dumps({"results": {"a.py": [{"type": "Secret Keyword", "hashed_secret": "1"}]}})
        head = json.dumps({"results": {"b.py": [{"type": "Secret Keyword", "hashed_secret": "2"}]}})
        self.assertFails("allowlist entry added",
                         [{"filename": ".secrets.baseline", "status": "modified", "patch": patch("x")}],
                         head={".secrets.baseline": head}, base={".secrets.baseline": base})

    def test_allowlist_detector_removed_fails(self):
        files, sides = self.baseline_case({"plugins_used": self.DETECTORS}, {"plugins_used": self.DETECTORS[1:]})
        self.assertFails("detector removed or changed: AWSKeyDetector", files, **sides)

    def test_allowlist_detector_limit_raised_fails(self):
        raised = [self.DETECTORS[0], {"name": "HexHighEntropyString", "limit": 5.0}]
        files, sides = self.baseline_case({"plugins_used": self.DETECTORS}, {"plugins_used": raised})
        self.assertFails("detector removed or changed: HexHighEntropyString", files, **sides)

    def test_allowlist_detector_added_passes(self):
        files, sides = self.baseline_case({"plugins_used": self.DETECTORS},
                                          {"plugins_used": self.DETECTORS + [{"name": "NewDetector"}]})
        self.assertPasses(files, **sides)

    def test_allowlist_filter_pattern_added_fails(self):
        wider = dict(self.LINE_FILTER, pattern=["^rev: x$", ".*"])
        files, sides = self.baseline_case({"filters_used": [self.LINE_FILTER]}, {"filters_used": [wider]})
        self.assertFails("gained", files, **sides)

    def test_allowlist_custom_filter_added_fails(self):
        exclude_all = {"path": "detect_secrets.filters.regex.should_exclude_file", "pattern": [".*"]}
        files, sides = self.baseline_case({"filters_used": []}, {"filters_used": [exclude_all]})
        self.assertFails("filter added", files, **sides)

    def test_allowlist_heuristic_filter_added_passes(self):
        heuristic = {"path": "detect_secrets.filters.heuristic.is_new_heuristic"}
        files, sides = self.baseline_case({"filters_used": []}, {"filters_used": [heuristic]})
        self.assertPasses(files, **sides)

    def test_allowlist_filter_pattern_removed_passes(self):
        narrower = dict(self.LINE_FILTER, pattern=[])
        files, sides = self.baseline_case({"filters_used": [self.LINE_FILTER]}, {"filters_used": [narrower]})
        self.assertPasses(files, **sides)

    # --- fails closed -------------------------------------------------------------------
    def test_partial_file_list_fails(self):
        self.assertFails("changed files (it stops at 3000)",
                         [{"filename": "src/app.py", "status": "added", "patch": patch("x")}], changed_files=3001)

    def test_partial_commit_list_fails(self):
        self.assertFails("commits (it stops at 250)",
                         [{"filename": "src/app.py", "status": "added", "patch": patch("x")}], commit_count=300)

    def test_invalid_path_regex_fails(self):
        bad = os.path.join(self.tmp, "bad-paths.txt")
        with open(bad, "w") as fh:
            fh.write("(unclosed\n")
        self.assertFails("invalid regular expression",
                         [{"filename": "src/app.py", "status": "added", "patch": patch("x")}], paths_file=bad)

    def test_malformed_allowlist_fails_closed(self):
        self.assertFails("could not run",
                         [{"filename": ".secrets.baseline", "status": "modified", "patch": patch("x")}],
                         head={".secrets.baseline": "not json"}, base={".secrets.baseline": "{}"})

    def test_unfetchable_base_of_file_without_diff_fails_closed(self):
        self.assertFails("unexpected error", [{"filename": "big.txt", "status": "modified"}],
                         head={"big.txt": "a\n"})

    def test_missing_terms_list_fails_closed(self):
        self.assertFails("could not run",
                         [{"filename": "src/app.py", "status": "added", "patch": patch("x")}],
                         terms_file=os.path.join(self.tmp, "missing.txt"))

    def test_missing_base_copy_fails_closed(self):
        self.assertFails("unexpected error",
                         [{"filename": ".pre-commit-config.yaml", "status": "modified", "patch": patch("x")}],
                         head={".pre-commit-config.yaml": "repos: []\n"})

    # --- workflows ----------------------------------------------------------------------
    @unittest.skipUnless(HAVE_ZIZMOR, "zizmor not installed")
    def test_risky_workflow_fails(self):
        wf = ("name: t\non: workflow_dispatch\npermissions: {}\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
              "    steps:\n      - uses: actions/checkout@v4\n      - run: echo \"${{ github.event.pull_request.title }}\"\n")
        self.assertFails("zizmor findings",
                         [{"filename": ".github/workflows/t.yml", "status": "added", "patch": patch("x")}],
                         head={".github/workflows/t.yml": wf})

    def new_workflow(self, jobs):
        path = ".github/workflows/t.yml"
        return [{"filename": path, "status": "added", "patch": patch("x")}], {"head": {path: workflow(jobs)}}

    def test_workflow_reporting_required_check_name_fails(self):
        files, sides = self.new_workflow("  secret-scan:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n")
        self.assertFails("could report a required check name", files, **sides)

    def test_workflow_with_expression_job_name_fails(self):
        files, sides = self.new_workflow(
            "  a:\n    name: ${{ github.event_name }}\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n")
        self.assertFails("could report a required check name", files, **sides)

    def test_workflow_with_partial_expression_job_name_fails(self):
        files, sides = self.new_workflow(
            "  a:\n    name: secret-${{ github.event_name }}\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n")
        self.assertFails("could report a required check name", files, **sides)

    @unittest.skipUnless(HAVE_ZIZMOR, "zizmor not installed")
    def test_workflow_with_matrix_job_name_passes(self):
        files, sides = self.new_workflow(
            "  a:\n    name: test (${{ matrix.os }})\n    strategy:\n      matrix:\n        os: [ubuntu-latest]\n"
            "    runs-on: ${{ matrix.os }}\n    steps:\n      - run: echo ok\n")
        self.assertPasses(files, **sides)

    def trusted_case(self, old, new, count=1):
        current = read(TRUSTED)
        self.assertIn(old, current, "fixture text not found in the trusted workflow")
        return self.modified(TRUSTED, current.replace(old, new, count))

    def test_trusted_workflow_job_skipped_fails(self):
        files, sides = self.trusted_case("  secret-scan:\n    name: secret-scan\n",
                                         "  secret-scan:\n    name: secret-scan\n    if: false\n")
        self.assertFails("a skipped required check counts as passed", files, **sides)

    def test_trusted_workflow_job_needs_fails(self):
        files, sides = self.trusted_case("  selftest:\n    name: selftest\n",
                                         "  selftest:\n    name: selftest\n    needs: precommit\n")
        self.assertFails("a skipped required check counts as passed", files, **sides)

    def test_trusted_workflow_step_skipped_fails(self):
        files, sides = self.trusted_case("      - name: Check the pull request\n",
                                         "      - name: Check the pull request\n        if: false\n")
        self.assertFails("has `if:`", files, **sides)

    def test_trusted_workflow_continue_on_error_fails(self):
        files, sides = self.trusted_case("  precommit:\n    name: precommit\n",
                                         "  precommit:\n    name: precommit\n    continue-on-error: true\n")
        self.assertFails("continue-on-error", files, **sides)

    def test_trusted_workflow_trigger_changed_fails(self):
        files, sides = self.trusted_case("  pull_request_target:\n", "  pull_request:\n")
        self.assertFails("the trigger must be pull_request_target only", files, **sides)

    def test_trusted_workflow_edited_type_removed_fails(self):
        files, sides = self.trusted_case("types: [opened, synchronize, reopened, edited]",
                                         "types: [opened, synchronize, reopened]")
        self.assertFails("must include types edited", files, **sides)

    def test_trusted_workflow_duplicate_producer_fails(self):
        current = read(TRUSTED)
        spoof = "\n  spoof:\n    name: selftest\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n"
        files, sides = self.modified(TRUSTED, current + spoof)
        self.assertFails("must come from exactly one job", files, **sides)

    def test_trusted_workflow_write_permission_fails(self):
        # The precommit job's own text, whatever runner it names.
        job = re.search(r"  precommit:\n    name: precommit\n    runs-on: \S+\n    timeout-minutes: \d+\n"
                        r"    permissions:\n      contents: read\n", read(TRUSTED))
        self.assertIsNotNone(job, "fixture text not found in the trusted workflow")
        files, sides = self.trusted_case(job.group(0), job.group(0).replace("contents: read", "contents: write"))
        self.assertFails("asks for write permission", files, **sides)

    PR_TESTS_ENV = "        working-directory: pr\n        env:\n          REQUIRE_ZIZMOR: \"1\"\n"

    def test_trusted_workflow_token_passed_to_pr_code_fails(self):
        files, sides = self.trusted_case(self.PR_TESTS_ENV, self.PR_TESTS_ENV + "          GH_TOKEN: ${{ github.token }}\n")
        self.assertFails("runs the PR's code and", files, **sides)

    def test_trusted_workflow_bracket_token_fails(self):
        files, sides = self.trusted_case(self.PR_TESTS_ENV, self.PR_TESTS_ENV + "          T: ${{ github['token'] }}\n")
        self.assertFails("outside the safe list", files, **sides)

    def test_trusted_workflow_whole_context_fails(self):
        files, sides = self.trusted_case(self.PR_TESTS_ENV, self.PR_TESTS_ENV + "          CTX: ${{ toJSON(github) }}\n")
        self.assertFails("outside the safe list", files, **sides)

    def test_trusted_workflow_persisted_credentials_fails(self):
        old = "          path: pr\n          persist-credentials: false\n"
        files, sides = self.trusted_case(old, "          path: pr\n")
        self.assertFails("without persist-credentials: false", files, **sides)

    def test_trusted_workflow_deleted_fails(self):
        self.assertFails("the required checks come from it", [{"filename": TRUSTED, "status": "removed"}])

    @unittest.skipUnless(HAVE_ZIZMOR, "zizmor not installed")
    def test_trusted_workflow_pin_bump_passes(self):
        files, sides = self.trusted_case("3d3c42e5aac5ba805825da76410c181273ba90b1", "1" * 40, count=-1)
        self.assertPasses(files, **sides)


class CommitMessageHook(unittest.TestCase):
    """The commit-msg hook checks a message's text. Git chooses where the message
    file lives (inside the main clone's .git for a worktree), so its path isn't checked."""

    def check(self, text, folder):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "BLOCKED_TERMS_FILE": os.path.join(tmp, "terms.txt")}
            script = os.path.join(ROOT, "scripts", "check_blocked_terms.py")
            for args in (["--add", "ZebraCorp"], ["--add", "--paths", "quokka"]):
                subprocess.run([sys.executable, script, *args], env=env, check=True, capture_output=True)
            message = os.path.join(tmp, folder, "COMMIT_EDITMSG")
            os.makedirs(os.path.dirname(message))
            with open(message, "w", encoding="utf-8") as fh:
                fh.write(text)
            return subprocess.run([sys.executable, script, "--message", message], env=env,
                                  capture_output=True, text=True).returncode

    def test_blocked_name_in_message_text_fails(self):
        self.assertEqual(self.check("Add the Zebra Corp importer\n", "worktrees"), 1)

    def test_blocked_path_name_in_message_location_passes(self):
        self.assertEqual(self.check("Add the importer\n", "quokka-clone"), 0)


class FileLengthHook(unittest.TestCase):
    """The pre-commit hook that keeps the app's source files under 500 lines."""

    def check(self, lines):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "module.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("".join(f"x{i} = {i}\n" for i in range(lines)))
            script = os.path.join(ROOT, "scripts", "check_file_length.py")
            return subprocess.run([sys.executable, script, path], capture_output=True, text=True).returncode

    def test_file_at_the_limit_passes(self):
        self.assertEqual(self.check(500), 0)

    def test_file_over_the_limit_fails(self):
        self.assertEqual(self.check(501), 1)


if __name__ == "__main__":
    unittest.main()
