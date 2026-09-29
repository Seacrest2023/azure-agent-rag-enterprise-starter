"""Tests for scripts/github_settings.py, run against a fake GitHub API.

The fake keeps the repository's settings in a JSON file: reads answer from it, and writes change it, so a
test can check what --apply sent and that the settings meet the baseline afterwards.

Run: python -m unittest discover -s tests/gate -t .
"""

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# SECURITY_CODE_ROOT points these tests at another copy of the code (see test_security_gate.py).
ROOT = os.path.abspath(os.environ.get("SECURITY_CODE_ROOT") or os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(ROOT, "scripts", "github_settings.py")
REPO = "o/r"
CHECKS = ["secret-scan", "precommit", "selftest", "security-critical-gate", "python"]

FAKE_GH = r'''
import json, os, re, sys
state_file, log_file = os.environ["FAKE_GH_STATE"], os.environ["FAKE_GH_LOG"]
state = json.load(open(state_file))
args = sys.argv[1:]
assert args[0] == "api", args
method, path, body, fields, i = "GET", None, None, {}, 1
while i < len(args):
    a = args[i]
    if a == "-X":
        method, i = args[i + 1], i + 2
    elif a == "--input":
        body, i = json.load(open(args[i + 1])), i + 2
    elif a in ("-f", "-F"):
        k, v = args[i + 1].split("=", 1)
        fields[k] = {"true": True, "false": False}.get(v, v) if a == "-F" else v
        i += 2
    else:
        path, i = a.split("?")[0], i + 1
with open(log_file, "a") as fh:
    fh.write(json.dumps({"method": method, "path": path, "body": body, "fields": fields}) + "\n")
if state.get("broken"):
    sys.exit(1)
repo = "repos/o/r/"
rel = path[len(repo):]
if method == "GET" and rel in state.get("broken_paths", []):
    sys.exit(1)
def done():
    json.dump(state, open(state_file, "w"))
    sys.exit(0)
def answer(value):
    print(json.dumps(value))
    sys.exit(0)
def missing():
    sys.stderr.write("gh: Not Found (HTTP 404)\n")
    sys.exit(1)
if rel == "rulesets":
    if method == "GET":
        answer([{"id": r["id"], "name": r["name"], "target": r["target"]} for r in state["rulesets"]])
    new = dict(body, id=100 + len(state["rulesets"]))
    state["rulesets"].append(new)
    done()
m = re.fullmatch(r"rulesets/(\d+)", rel)
if m:
    found = [r for r in state["rulesets"] if r["id"] == int(m.group(1))]
    if not found:
        missing()
    if method == "GET":
        answer(found[0])
    found[0].clear()
    found[0].update(dict(body, id=int(m.group(1))))
    done()
if rel in ("actions/permissions", "actions/permissions/workflow"):
    key = "actions" if rel == "actions/permissions" else "workflow"
    if method == "GET":
        answer(state[key])
    state[key].update(fields)
    done()
if rel == "vulnerability-alerts":
    if method == "GET":
        sys.exit(0) if state["alerts"] else missing()
    state["alerts"] = True
    done()
if rel == "automated-security-fixes":
    if method == "GET":
        answer({"enabled": state["fixes"], "paused": False})
    state["fixes"] = True
    done()
m = re.fullmatch(r"environments/([^/]+)(/deployment-branch-policies)?(?:/(\d+))?", rel)
if m:
    env = state["environments"].get(m.group(1))
    if not m.group(2):
        if method == "GET":
            answer(env) if env is not None else missing()
        state["environments"][m.group(1)] = dict(env or {"branches": []}, **body)
        done()
    if env is None:
        missing()
    if method == "GET":
        answer({"branch_policies": [{"id": n, "name": b} for n, b in enumerate(env["branches"])]})
    if method == "DELETE":
        env["branches"][int(m.group(3))] = None
        env["branches"] = [b for b in env["branches"] if b is not None]
        done()
    env["branches"].append(fields["name"])
    done()
missing()
'''


def baseline_ruleset(**changes):
    ruleset = {
        "id": 1, "name": "main", "target": "branch", "enforcement": "active", "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"}, {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {
                "required_approving_review_count": 0, "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": True, "require_last_push_approval": False,
                "required_review_thread_resolution": True, "require_extra_approval_for_unattributed_changes": True,
                "allowed_merge_methods": ["squash"]}},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [{"context": c, "integration_id": 15368} for c in CHECKS]}},
        ],
    }
    ruleset.update(changes)
    return ruleset


def rule(ruleset, kind):
    return next(r for r in ruleset["rules"] if r["type"] == kind)


def baseline_state():
    return {
        "rulesets": [baseline_ruleset()],
        "actions": {"enabled": True, "allowed_actions": "all", "sha_pinning_required": True},
        "workflow": {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False},
        "alerts": True,
        "fixes": True,
        "environments": {"dev": {"deployment_branch_policy": {"protected_branches": False,
                                                              "custom_branch_policies": True},
                                 "branches": ["main"]}},
    }


class GitHubSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # A copy of the script next to its own .claude/security-stack.json.
        os.makedirs(os.path.join(self.tmp, "scripts"))
        os.makedirs(os.path.join(self.tmp, ".claude"))
        shutil.copy(SCRIPT, os.path.join(self.tmp, "scripts"))
        self.write_stack()
        fake = os.path.join(self.tmp, "fake_gh.py")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write(FAKE_GH)
        self.gh = json.dumps([sys.executable, fake])
        self.state_file = os.path.join(self.tmp, "state.json")
        self.log_file = os.path.join(self.tmp, "log.jsonl")

    def write_stack(self, **github):
        values = {"repository": REPO, "default_branch": "main", "deploy_environment": "dev",
                  "required_checks": CHECKS, "required_checks_in_ruleset_now": CHECKS, "merge_methods": ["squash"]}
        values.update(github)
        with open(os.path.join(self.tmp, ".claude", "security-stack.json"), "w", encoding="utf-8") as fh:
            json.dump({"github": values}, fh)

    def run_script(self, state, *args):
        with open(self.state_file, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        open(self.log_file, "w").close()
        env = dict(os.environ, GITHUB_SETTINGS_GH=self.gh, FAKE_GH_STATE=self.state_file, FAKE_GH_LOG=self.log_file)
        return subprocess.run([sys.executable, os.path.join(self.tmp, "scripts", "github_settings.py"), *args],
                              capture_output=True, text=True, env=env, timeout=120)

    def state_after(self):
        with open(self.state_file, encoding="utf-8") as fh:
            return json.load(fh)

    def writes(self):
        with open(self.log_file, encoding="utf-8") as fh:
            return [c for c in map(json.loads, fh) if c["method"] != "GET"]

    def test_baseline_settings_pass(self):
        result = self.run_script(baseline_state())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.writes(), [])

    def test_stricter_settings_pass(self):
        state = baseline_state()
        ruleset = state["rulesets"][0]
        rule(ruleset, "pull_request")["parameters"].update(required_approving_review_count=1,
                                                             require_last_push_approval=True)
        rule(ruleset, "required_status_checks")["parameters"]["required_status_checks"].append(
            {"context": "codeql", "integration_id": 57789})
        ruleset["rules"].append({"type": "required_signatures"})
        state["actions"]["allowed_actions"] = "selected"
        result = self.run_script(state)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_each_shortfall_is_reported(self):
        def ruleset_with(change):
            state = baseline_state()
            change(state["rulesets"][0])
            return state

        def pr_params(r):
            return rule(r, "pull_request")["parameters"]

        def check_params(r):
            return rule(r, "required_status_checks")["parameters"]

        cases = [
            ("no ruleset on the default branch", dict(baseline_state(), rulesets=[])),
            ("enforcement is 'evaluate'", ruleset_with(lambda r: r.update(enforcement="evaluate"))),
            ("bypass list", ruleset_with(lambda r: r.update(bypass_actors=[{"actor_id": 5, "actor_type": "RepositoryRole",
                                                                             "bypass_mode": "always"}]))),
            ("no non_fast_forward rule", ruleset_with(lambda r: r["rules"].pop(1))),
            ("code-owner review is off", ruleset_with(lambda r: pr_params(r).update(require_code_owner_review=False))),
            ("stale approvals", ruleset_with(lambda r: pr_params(r).update(dismiss_stale_reviews_on_push=False))),
            ("review threads needn't be resolved", ruleset_with(lambda r: pr_params(r).update(
                required_review_thread_resolution=False))),
            ("unattributed authors", ruleset_with(lambda r: pr_params(r).update(
                require_extra_approval_for_unattributed_changes=False))),
            ("merge methods allowed beyond", ruleset_with(lambda r: pr_params(r).update(
                allowed_merge_methods=["squash", "merge"]))),
            ("up to date", ruleset_with(lambda r: check_params(r).update(strict_required_status_checks_policy=False))),
            ("required check 'python' is missing", ruleset_with(lambda r: check_params(r)["required_status_checks"].pop())),
            ("isn't tied to GitHub Actions", ruleset_with(lambda r: check_params(r)["required_status_checks"][0].update(
                integration_id=1))),
            ("not pinned to a full commit SHA", dict(baseline_state(), actions={"enabled": True, "allowed_actions": "all",
                                                                                "sha_pinning_required": False})),
            ("Actions is off", dict(baseline_state(), actions={"enabled": False, "allowed_actions": "all",
                                                               "sha_pinning_required": True})),
            ("read-only by default", dict(baseline_state(), workflow={"default_workflow_permissions": "write",
                                                                      "can_approve_pull_request_reviews": False})),
            ("Actions can approve", dict(baseline_state(), workflow={"default_workflow_permissions": "read",
                                                                     "can_approve_pull_request_reviews": True})),
            ("Dependabot alerts are off", dict(baseline_state(), alerts=False)),
            ("security updates are off", dict(baseline_state(), fixes=False)),
            ("dev environment doesn't exist", dict(baseline_state(), environments={})),
            ("deploys from ['main', 'feature']", dict(baseline_state(), environments={"dev": {
                "deployment_branch_policy": {"custom_branch_policies": True}, "branches": ["main", "feature"]}})),
            ("isn't limited to named branches", dict(baseline_state(), environments={"dev": {
                "deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": False},
                "branches": []}})),
            ("isn't limited to named branches", dict(baseline_state(), environments={"dev": {
                "deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": True},
                "branches": ["main"]}})),
            ("no ruleset on the default branch", ruleset_with(lambda r: r["conditions"]["ref_name"].update(
                include=["~ALL"], exclude=["refs/heads/main"]))),
            ("no ruleset on the default branch", ruleset_with(lambda r: r["conditions"]["ref_name"].update(
                exclude=["refs/heads/m*"]))),
        ]
        for words, state in cases:
            with self.subTest(words):
                result = self.run_script(state)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(words, result.stdout)
                self.assertEqual(self.writes(), [], "checking must never write")

    def test_apply_raises_every_shortfall(self):
        state = baseline_state()
        ruleset = state["rulesets"][0]
        ruleset.update(enforcement="disabled", bypass_actors=[{"actor_id": 5, "actor_type": "RepositoryRole"}])
        pr = rule(ruleset, "pull_request")["parameters"]
        pr.update(require_code_owner_review=False, allowed_merge_methods=["merge", "squash", "rebase"],
                  required_review_thread_resolution=False, require_extra_approval_for_unattributed_changes=False)
        rule(ruleset, "required_status_checks")["parameters"]["required_status_checks"].pop()
        state.update(workflow={"default_workflow_permissions": "write", "can_approve_pull_request_reviews": True},
                     alerts=False, fixes=False, environments={})
        state["actions"]["sha_pinning_required"] = False
        result = self.run_script(state, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("every GitHub setting is at the baseline or stricter", result.stdout)
        after = self.state_after()
        raised = after["rulesets"][0]
        self.assertEqual((raised["id"], raised["enforcement"], raised["bypass_actors"]), (1, "active", []))
        raised_pr = rule(raised, "pull_request")["parameters"]
        self.assertEqual(raised_pr["allowed_merge_methods"], ["squash"])
        self.assertTrue(raised_pr["required_review_thread_resolution"])
        self.assertTrue(raised_pr["require_extra_approval_for_unattributed_changes"])
        self.assertEqual(after["environments"]["dev"]["branches"], ["main"])

    def test_apply_creates_the_ruleset_when_there_is_none(self):
        result = self.run_script(dict(baseline_state(), rulesets=[]), "--apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        posted = [w for w in self.writes() if w["method"] == "POST" and w["path"].endswith("/rulesets")]
        self.assertEqual(len(posted), 1)
        body = posted[0]["body"]
        self.assertEqual((body["target"], body["enforcement"], body["bypass_actors"]), ("branch", "active", []))
        self.assertEqual(body["conditions"]["ref_name"]["include"], ["~DEFAULT_BRANCH"])
        checks = rule(body, "required_status_checks")["parameters"]["required_status_checks"]
        self.assertEqual([c["context"] for c in checks], CHECKS)
        pr = rule(body, "pull_request")["parameters"]
        self.assertTrue(pr["required_review_thread_resolution"])
        self.assertTrue(pr["require_extra_approval_for_unattributed_changes"])

    def test_apply_never_lowers_a_stricter_setting(self):
        state = baseline_state()
        ruleset = state["rulesets"][0]
        pr = rule(ruleset, "pull_request")["parameters"]
        pr.update(required_approving_review_count=2, require_last_push_approval=True,
                  required_review_thread_resolution=True, require_code_owner_review=False)
        rule(ruleset, "required_status_checks")["parameters"]["required_status_checks"].append(
            {"context": "codeql", "integration_id": 57789})
        ruleset["rules"].append({"type": "required_signatures"})
        state["actions"].update(allowed_actions="selected", sha_pinning_required=False)
        state["environments"]["dev"] = {
            "deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": False},
            "branches": ["main"],
            "protection_rules": [{"type": "wait_timer", "wait_timer": 30},
                                 {"type": "required_reviewers", "prevent_self_review": True,
                                  "reviewers": [{"type": "User", "reviewer": {"id": 7}}]},
                                 {"type": "branch_policy"}]}
        expected_kept = copy.deepcopy(pr)
        result = self.run_script(state, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = self.state_after()
        raised = after["rulesets"][0]
        params = rule(raised, "pull_request")["parameters"]
        for key in ("required_approving_review_count", "require_last_push_approval",
                    "required_review_thread_resolution"):
            self.assertEqual(params[key], expected_kept[key], key)
        self.assertTrue(params["require_code_owner_review"])
        contexts = [c["context"] for c in rule(raised, "required_status_checks")["parameters"]["required_status_checks"]]
        self.assertIn("codeql", contexts)
        self.assertIn("required_signatures", [r["type"] for r in raised["rules"]])
        self.assertEqual(after["actions"]["allowed_actions"], "selected")
        # Updating an environment drops the protections the update doesn't name, so they're carried forward.
        env_put = [w for w in self.writes() if w["method"] == "PUT" and w["path"].endswith("/environments/dev")]
        self.assertEqual(len(env_put), 1)
        self.assertEqual({k: env_put[0]["body"].get(k) for k in ("wait_timer", "prevent_self_review", "reviewers")},
                         {"wait_timer": 30, "prevent_self_review": True, "reviewers": [{"type": "User", "id": 7}]})

    def test_only_checks_recorded_as_ready_are_required(self):
        # A check listed in required_checks but not yet in required_checks_in_ruleset_now isn't added:
        # a required check that can't run blocks every pull request. It's still reported as missing.
        self.write_stack(required_checks=[*CHECKS, "codeql"], required_checks_in_ruleset_now=CHECKS)
        result = self.run_script(dict(baseline_state(), rulesets=[]), "--apply")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("required check 'codeql' is missing; --apply adds it once", result.stdout)
        contexts = [c["context"] for c in rule(self.state_after()["rulesets"][0],
                                               "required_status_checks")["parameters"]["required_status_checks"]]
        self.assertNotIn("codeql", contexts)
        # Taking a check off the ready list doesn't hide it: required_checks, which the gate protects,
        # is the baseline.
        self.write_stack(required_checks=CHECKS, required_checks_in_ruleset_now=CHECKS[:-1])
        state = baseline_state()
        rule(state["rulesets"][0], "required_status_checks")["parameters"]["required_status_checks"].pop()
        result = self.run_script(state)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("required check 'python' is missing", result.stdout)
        # The ready list only says which baseline checks may be added; a name only there isn't added.
        self.write_stack(required_checks=CHECKS, required_checks_in_ruleset_now=[*CHECKS, "codeql"])
        result = self.run_script(dict(baseline_state(), rulesets=[]), "--apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        contexts = [c["context"] for c in rule(self.state_after()["rulesets"][0],
                                               "required_status_checks")["parameters"]["required_status_checks"]]
        self.assertEqual(contexts, CHECKS)

    def test_unreadable_settings_fail_closed(self):
        # A failed read is unreadable (exit 2), not a setting that's off, and --apply writes nothing.
        states = [dict(baseline_state(), broken=True), dict(baseline_state(), actions=[]),
                  dict(baseline_state(), workflow="read")] + [
            dict(baseline_state(), broken_paths=[path])
            for path in ("vulnerability-alerts", "automated-security-fixes", "environments/dev")]
        for state in states:
            for args in ([], ["--apply"]):
                with self.subTest(broken=state.get("broken_paths", state.get("broken")), args=args):
                    result = self.run_script(state, *args)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn("Couldn't check", result.stderr)
                    self.assertEqual(self.writes(), [])

    def test_missing_project_values_fail_closed(self):
        for github in [{"repository": ""}, {"required_checks": []}, {"required_checks_in_ruleset_now": []},
                       {"merge_methods": None}, {"deploy_environment": ""}, {"required_checks": "python"},
                       {"merge_methods": "squash"}, {"repository": 5}]:
            with self.subTest(github=github):
                self.write_stack(**github)
                result = self.run_script(baseline_state())
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_unknown_arguments_are_refused(self):
        result = self.run_script(baseline_state(), "--force")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.writes(), [])


if __name__ == "__main__":
    unittest.main()
