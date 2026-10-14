"""Tests for the infrastructure checks' steps in .github/workflows/infra.yml (checks 74 and 75).

Each test runs a step's own script, taken from the workflow, in a throwaway git repository, the way
Actions runs it (bash -eo pipefail, with the step's env), with stand-ins in RUNNER_TEMP for the Bicep
CLI and Checkov. The Bicep stand-in behaves as the file it's handed says; the Checkov stand-in writes
the report the test hands it. CI runs the default branch's copy of these tests against a PR's
workflow (selftest), so a PR can't weaken a step and its tests together.

Run: python -m unittest discover -s tests/gate -t .
Needs bash, git, python3 and PyYAML.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

import yaml

# SECURITY_CODE_ROOT points these tests at another copy of the code (see test_security_gate.py).
ROOT = os.path.abspath(os.environ.get("SECURITY_CODE_ROOT") or os.path.join(os.path.dirname(__file__), "..", ".."))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "infra.yml")
BASH = shutil.which("bash")

# The Bicep CLI's stand-in: records each call as its command and file, NUL-separated, in the file
# BICEP_CALLS names. A file containing BUILD_ERROR fails to build, LINT_WARNING gets a diagnostic,
# and LINT_CRASH makes lint exit 1 without a word.
BICEP = r"""#!/usr/bin/env bash
printf '%s %s\0' "$1" "$2" >> "$BICEP_CALLS"
case "$1" in
  build) if grep -q BUILD_ERROR -- "$2"; then echo "$2: Error BCP018" >&2; exit 1; fi ;;
  lint)
    if grep -q LINT_CRASH -- "$2"; then exit 1; fi
    if grep -q LINT_WARNING -- "$2"; then echo "$2: Warning no-unused-params"; fi ;;
esac
exit 0
"""

# Checkov's stand-in: records its arguments, one per line, and its update-check setting; copies the
# report CHECKOV_REPORT names, if any, to the JSON path in --output-file-path; exits with CHECKOV_EXIT.
CHECKOV = r"""#!/usr/bin/env bash
printf '%s\n' "$@" > "$CHECKOV_ARGS"
printf '%s' "${CKV_SKIP_PACKAGE_UPDATE_CHECK-unset}" > "$CHECKOV_UPDATE_CHECK"
while [ "$#" -gt 0 ]; do
  if [ "$1" = --output-file-path ]; then out=${2#console,}; fi
  shift
done
if [ -n "${CHECKOV_REPORT-}" ]; then cp -- "$CHECKOV_REPORT" "$out"; fi
exit "${CHECKOV_EXIT:-0}"
"""

# A Bicep scan that read eight resources, and the bare summary Checkov writes when it read nothing.
READ = {"check_type": "bicep", "summary": {"passed": 4, "failed": 0, "skipped": 0, "parsing_errors": 0, "resource_count": 8}}
NOTHING = {"passed": 0, "failed": 0, "skipped": 0, "parsing_errors": 0, "resource_count": 0, "checkov_version": "3.3.23"}


def workflow_step(job, name_start):
    """The job's step whose name starts with name_start, as the workflow has it."""
    with open(WORKFLOW, encoding="utf-8") as fh:
        steps = yaml.safe_load(fh)["jobs"][job]["steps"]
    return next(step for step in steps if step.get("name", "").startswith(name_start))


class StepTest(unittest.TestCase):
    """A throwaway repository, and a RUNNER_TEMP for the stand-ins."""

    def setUp(self):
        self.assertIsNotNone(BASH, "these tests need bash")
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "repo")
        self.runner_temp = os.path.join(self.tmp, "runner")
        os.makedirs(self.runner_temp)
        subprocess.run(["git", "init", "-q", self.repo], check=True)

    def path(self, name):
        """A path in the temporary folder, as bash reads it."""
        return os.path.join(self.tmp, name).replace("\\", "/")

    def add(self, files):
        """Track the files (git ls-files lists what's staged)."""
        for name, text in files.items():
            full = os.path.join(self.repo, name)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        subprocess.run(["git", "add", "--", *files], cwd=self.repo, check=True)

    def stand_in(self, name, script):
        full = os.path.join(self.runner_temp, name)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(script)
        os.chmod(full, 0o755)

    def run_step(self, job, name_start, **extra_env):
        """Run the step as Actions does: its exit code, and its output and errors together."""
        step = workflow_step(job, name_start)
        env = dict(os.environ)
        env.update(RUNNER_TEMP=self.runner_temp.replace("\\", "/"), GITHUB_WORKSPACE=self.repo.replace("\\", "/"))
        env.update({key: str(value) for key, value in step.get("env", {}).items()})
        env.update(extra_env)
        result = subprocess.run([BASH, "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
                                cwd=self.repo, env=env, capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr


class BicepStep(StepTest):
    """What the build-and-lint step fails on (check 74)."""

    def setUp(self):
        super().setUp()
        self.calls_file = self.path("bicep-calls")
        self.stand_in("bicep", BICEP)

    def check(self):
        """The step's exit code, its output, and the Bicep CLI's calls as (command, file) pairs."""
        code, out = self.run_step("bicep", "Build and lint", BICEP_CALLS=self.calls_file)
        calls = []
        if os.path.exists(self.calls_file):
            with open(self.calls_file, encoding="utf-8", newline="") as fh:
                calls = [tuple(call.split(" ", 1)) for call in fh.read().split("\0") if call]
        return code, out, calls

    def test_no_bicep_files_passes_without_running_bicep(self):
        self.add({"README.md": "no infrastructure yet\n"})
        code, out, calls = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("No Bicep files.", out)
        self.assertEqual(calls, [])

    def test_clean_files_are_each_built_and_linted(self):
        self.add({"infra/main.bicep": "clean\n", "infra/modules/app.bicep": "clean\n", "notes.txt": "not bicep\n"})
        code, out, calls = self.check()
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(calls), [("build", "./infra/main.bicep"), ("build", "./infra/modules/app.bicep"),
                                         ("lint", "./infra/main.bicep"), ("lint", "./infra/modules/app.bicep")])

    def test_a_lint_diagnostic_fails_and_is_shown(self):
        self.add({"infra/main.bicep": "LINT_WARNING\n"})
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertIn("Warning no-unused-params", out)
        self.assertIn("::error file=infra/main.bicep::Bicep lint findings", out)

    def test_a_lint_that_fails_without_a_diagnostic_fails(self):
        self.add({"infra/main.bicep": "LINT_CRASH\n"})
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertIn("::error file=infra/main.bicep::Bicep lint findings", out)

    def test_a_build_failure_fails_and_the_other_files_are_still_checked(self):
        self.add({"a.bicep": "BUILD_ERROR\n", "b.bicep": "LINT_WARNING\n"})
        code, out, calls = self.check()
        self.assertEqual(code, 1)
        self.assertIn("::error file=a.bicep::Bicep build failed", out)
        self.assertIn("::error file=b.bicep::Bicep lint findings", out)
        self.assertNotIn(("lint", "./a.bicep"), calls)

    def test_any_file_name_is_one_file(self):
        # A space in a tracked name, a name like an option, and a line break where
        # the file system allows one (Windows doesn't; CI runs Linux).
        names = ["infra/with space.bicep", "--help.bicep"] + (["infra/two\nlines.bicep"] if os.name != "nt" else [])
        self.add({name: "clean\n" for name in names})
        code, out, calls = self.check()
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(file for command, file in calls if command == "build"), sorted(f"./{n}" for n in names))


class CheckovStep(StepTest):
    """What the scan step fails on (check 75)."""

    def setUp(self):
        super().setUp()
        self.args_file = self.path("checkov-args")
        self.update_check_file = self.path("checkov-update-check")
        self.stand_in(os.path.join("checkov", "bin", "checkov"), CHECKOV)

    def scan(self, report=None, raw=None, exit_code=0):
        """Run the step, with Checkov writing `report` as JSON, or `raw` text, or nothing: the exit code and output."""
        written = os.path.join(self.runner_temp, "checkov.json")
        if os.path.exists(written):
            os.remove(written)
        env = {"CHECKOV_ARGS": self.args_file, "CHECKOV_UPDATE_CHECK": self.update_check_file,
               "CHECKOV_EXIT": str(exit_code)}
        if report is not None or raw is not None:
            with open(self.path("report.json"), "w", encoding="utf-8") as fh:
                fh.write(raw if raw is not None else json.dumps(report))
            env["CHECKOV_REPORT"] = self.path("report.json")
        return self.run_step("checkov", "Scan", **env)

    def test_scans_bicep_offline(self):
        self.add({"infra/main.bicep": "resources\n"})
        code, out = self.scan(READ)
        self.assertEqual(code, 0, out)
        with open(self.args_file, encoding="utf-8") as fh:
            args = fh.read().splitlines()
        self.assertIn("--skip-download", args)
        self.assertEqual(args[args.index("--framework") + 1], "bicep")
        with open(self.update_check_file, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "true")

    def test_a_finding_fails(self):
        self.add({"infra/main.bicep": "resources\n"})
        self.assertEqual(self.scan(READ, exit_code=1)[0], 1)

    def test_a_scan_that_read_nothing_fails(self):
        self.add({"infra/main.bicep": "resources\n"})
        code, out = self.scan(NOTHING)
        self.assertEqual(code, 1)
        self.assertIn("::error::Checkov read no Bicep resources", out)

    def test_a_parse_error_fails(self):
        self.add({"infra/main.bicep": "resources\n"})
        report = {"check_type": "bicep", "summary": dict(READ["summary"], parsing_errors=1)}
        code, out = self.scan(report)
        self.assertEqual(code, 1)
        self.assertIn("::error::Checkov read no Bicep resources, or failed to parse a file", out)

    def test_no_report_fails(self):
        self.add({"infra/main.bicep": "resources\n"})
        code, out = self.scan()
        self.assertEqual(code, 1)
        self.assertIn("::error::Checkov wrote no readable report", out)

    def test_a_report_that_isnt_json_fails(self):
        self.add({"infra/main.bicep": "resources\n"})
        code, out = self.scan(raw="not json")
        self.assertEqual(code, 1)
        self.assertIn("::error::Checkov wrote no readable report", out)

    def test_a_report_for_several_frameworks_is_read_for_bicep(self):
        self.add({"infra/main.bicep": "resources\n"})
        arm = {"check_type": "arm", "summary": dict(READ["summary"], resource_count=0)}
        self.assertEqual(self.scan([arm, READ])[0], 0)
        self.assertEqual(self.scan([dict(READ, check_type="arm")])[0], 1)

    def test_with_no_bicep_files_checkov_alone_decides(self):
        self.add({"README.md": "no infrastructure yet\n"})
        self.assertEqual(self.scan()[0], 0)
        self.assertEqual(self.scan(exit_code=1)[0], 1)


if __name__ == "__main__":
    unittest.main()
