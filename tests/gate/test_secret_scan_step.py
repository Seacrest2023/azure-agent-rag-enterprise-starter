"""Tests for the secret-scan job's file selection in .github/workflows/security-gate.yml.

The job's scan step decides which files detect-secrets sees on a pull request. These
tests run that step's own script, taken from the workflow, in a throwaway git repository,
with a stand-in for detect-secrets-hook that records the arguments it was handed. CI runs
the default branch's copy of these tests against a PR's workflow (selftest), so a PR can't
narrow the scan and its tests together.

Run: python -m unittest discover -s tests/gate -t .
Needs bash, git and PyYAML.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

import yaml

# SECURITY_CODE_ROOT points these tests at another copy of the code (see test_security_gate.py).
ROOT = os.path.abspath(os.environ.get("SECURITY_CODE_ROOT") or os.path.join(os.path.dirname(__file__), "..", ".."))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "security-gate.yml")
BASH = shutil.which("bash")
# The stand-in for detect-secrets-hook: records its arguments, one per line, in the file SCAN_ARGS names.
STUB = "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$SCAN_ARGS\"\n"


def scan_script():
    """The run script of the secret-scan job's scan step, as the workflow has it."""
    with open(WORKFLOW, encoding="utf-8") as fh:
        steps = yaml.safe_load(fh)["jobs"]["secret-scan"]["steps"]
    return next(step["run"] for step in steps if step.get("name", "").startswith("Scan"))


class SecretScanStep(unittest.TestCase):
    """What the scan step hands detect-secrets-hook for the files a pull request adds, changes, renames or deletes."""

    def setUp(self):
        self.assertIsNotNone(BASH, "these tests need bash")
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "repo")
        stub_dir = os.path.join(self.tmp, "bin")
        os.makedirs(stub_dir)
        stub = os.path.join(stub_dir, "detect-secrets-hook")
        with open(stub, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(STUB)
        os.chmod(stub, 0o755)
        self.args_file = os.path.join(self.tmp, "args.txt").replace("\\", "/")
        self.env = dict(os.environ, SCAN_ARGS=self.args_file, PATH=stub_dir + os.pathsep + os.environ.get("PATH", ""))
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.base = self.commit({"a.txt": "a\n", "b.txt": "b\n", "keep.txt": "keep\n", ".secrets.baseline": "{}\n"})

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
                              cwd=self.repo, check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, files=None, delete=(), rename=()):
        for name, text in (files or {}).items():
            with open(os.path.join(self.repo, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        for name in delete:
            self.git("rm", "-q", "--", name)
        for old, new in rename:
            self.git("mv", "--", old, new)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")
        return self.git("rev-parse", "HEAD")

    def scan(self, base=None, head=None):
        """Run the step: its exit code, and the arguments the scanner got (None if it never ran)."""
        if os.path.exists(self.args_file):
            os.remove(self.args_file)
        env = dict(self.env, BASE_SHA=base or self.base, HEAD_SHA=head or self.git("rev-parse", "HEAD"))
        result = subprocess.run([BASH, "-c", scan_script()], cwd=self.repo, env=env, capture_output=True, text=True)
        if not os.path.exists(self.args_file):
            return result.returncode, None
        with open(self.args_file, encoding="utf-8") as fh:
            return result.returncode, fh.read().splitlines()

    def files_scanned(self, args):
        """The file names after the options, which must end with "--"."""
        self.assertIsNotNone(args, "the scanner never ran")
        self.assertEqual(args[:3], ["--baseline", ".secrets.baseline", "--"])
        return sorted(args[3:])

    def test_scans_what_the_pr_adds_or_changes(self):
        # Changed and added files, and a renamed file at its new path; not deleted files or the baseline.
        self.commit({"a.txt": "changed\n", "new.txt": "new\n", ".secrets.baseline": "{ }\n"},
                    delete=["b.txt"], rename=[("keep.txt", "moved.txt")])
        code, args = self.scan()
        self.assertEqual(code, 0)
        self.assertEqual(self.files_scanned(args), ["a.txt", "moved.txt", "new.txt"])

    def test_a_file_named_like_an_option_is_scanned_as_a_file(self):
        # Without "--", detect-secrets-hook would read --help as an option and exit 0 without scanning.
        self.commit({"--help": "not an option\n", "a.txt": "changed\n"})
        code, args = self.scan()
        self.assertEqual(code, 0)
        self.assertEqual(self.files_scanned(args), ["--help", "a.txt"])

    def test_only_the_baseline_changed_scans_nothing(self):
        self.commit({".secrets.baseline": "{ }\n"})
        self.assertEqual(self.scan(), (0, None))

    def test_a_base_commit_not_in_the_checkout_fails(self):
        self.commit({"a.txt": "changed\n"})
        code, args = self.scan(base="0" * 40)
        self.assertNotEqual(code, 0)
        self.assertIsNone(args)

    def test_another_checkout_fails(self):
        self.commit({"a.txt": "changed\n"})
        code, args = self.scan(head=self.base)
        self.assertNotEqual(code, 0)
        self.assertIsNone(args)


if __name__ == "__main__":
    unittest.main()
