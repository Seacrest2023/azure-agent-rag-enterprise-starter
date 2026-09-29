#!/usr/bin/env python3
"""Check the repository's GitHub settings against the baseline, and raise any that fall short.

  python scripts/github_settings.py            # check only (read-only): exit 0 all at baseline or stricter,
                                               # 1 something falls short, 2 something couldn't be read
  python scripts/github_settings.py --apply    # raise what falls short, then check again

The baseline is Phase 4 of docs/security-setup-prompt.md, with this project's values from
.claude/security-stack.json: the repository, the default branch, the deploy environment, the merge
methods, and the required checks. Every check in required_checks must be required; --apply adds only those
also in required_checks_in_ruleset_now, so a check that can't run yet is never required, and one that isn't
there yet is still reported. A setting stricter than the baseline counts as meeting it, and --apply never
lowers one: it keeps required approvals, extra required checks, extra rules, a narrower list of allowed
actions, and the deploy environment's reviewers and wait timer.

The settings:
  - a ruleset that covers the default branch and doesn't exclude it: active, no bypass list, no deletion
    or force push, a pull request with code-owner review and stale approvals dismissed, review threads
    resolved before merging, one more approval for changes by authors not linked to a GitHub account, only
    the recorded merge methods, and the required checks from GitHub Actions on an up-to-date branch
  - Actions: enabled, every action pinned to a full commit SHA, a read-only workflow token, and Actions
    can't approve pull requests
  - Dependabot alerts and security updates on
  - the deploy environment, deployable from the default branch only

It calls the GitHub CLI (`gh api`), signed in as a repository admin. GITHUB_SETTINGS_GH, a JSON list,
replaces the gh command (the tests use it).
"""

import fnmatch
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STACK = os.path.join(ROOT, ".claude", "security-stack.json")
ACTIONS_APP = 15368  # GitHub Actions, the app that reports the required checks
RULESET_NAME = "main"


class Unreadable(Exception):
    """A setting that couldn't be read or written."""


def gh(*args, body=None):
    """Run `gh api ...`; return (exit code, stdout, stderr). body, a dict, is sent as the request's JSON."""
    command = json.loads(os.environ["GITHUB_SETTINGS_GH"]) if os.environ.get("GITHUB_SETTINGS_GH") else ["gh"]
    input_file = None
    try:
        if body is not None:
            fd, input_file = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(body, fh)
            args = args + ("--input", input_file)
        result = subprocess.run(command + ["api", *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise Unreadable(f"gh api {' '.join(args)}: {exc}") from exc
    finally:
        if input_file:
            os.unlink(input_file)
    return result.returncode, result.stdout, result.stderr


def read(path):
    """GET path: its JSON ({} for an empty answer), or None when GitHub answers 404 (absent, or off).
    Any other failure can't be read."""
    code, out, err = gh(path)
    if code != 0:
        if "(HTTP 404)" in err:
            return None
        raise Unreadable(f"GET {path} failed")
    if not out.strip():
        return {}
    try:
        return json.loads(out)
    except ValueError as exc:
        raise Unreadable(f"GET {path} didn't return JSON") from exc


def get(path, kind=dict):
    """GET path, which must answer with a JSON object (or kind); anything else can't be read."""
    value = read(path)
    if not isinstance(value, kind):
        raise Unreadable(f"GET {path} didn't return the expected {kind.__name__}")
    return value


def put(method, path, body=None, fields=()):
    args = ("-X", method, path)
    for flag, value in fields:
        args += (flag, value)
    code, _, _ = gh(*args, body=body)
    if code != 0:
        raise Unreadable(f"{method} {path} failed")


def project():
    """This project's values from .claude/security-stack.json."""
    try:
        with open(STACK, encoding="utf-8") as fh:
            values = json.load(fh)["github"]
        repo, branch = values["repository"], values["default_branch"]
        required, ready = values["required_checks"], values["required_checks_in_ruleset_now"]
        methods, env = values["merge_methods"], values["deploy_environment"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Unreadable(f"{STACK}: {exc}") from exc
    if not all(isinstance(x, list) and x for x in (required, ready, methods)):
        raise Unreadable(f"{STACK}: the required checks and merge methods must be lists, and not empty")
    if not all(isinstance(x, str) and x for x in [*required, *ready, *methods, repo, branch, env]) or "/" not in repo:
        raise Unreadable(f"{STACK}: the repository, default branch, deploy environment, required checks or "
                         "merge methods are missing")
    return {"repo": repo, "branch": branch, "checks": ready, "methods": methods, "env": env,
            "all_checks": required}


# --- the ruleset ----------------------------------------------------------------------------------------

def covers_default_branch(ruleset, branch):
    """Whether the ruleset's branch conditions include the default branch and don't exclude it."""
    refs = (ruleset.get("conditions") or {}).get("ref_name") or {}
    ref = f"refs/heads/{branch}"

    def hits(patterns):
        return any(pattern in ("~ALL", "~DEFAULT_BRANCH") or fnmatch.fnmatchcase(ref, pattern)
                   for pattern in patterns or [] if isinstance(pattern, str))
    return hits(refs.get("include")) and not hits(refs.get("exclude"))


def find_ruleset(p):
    """The full ruleset on the default branch, or None. Prefers the one named like the baseline's."""
    listed = get(f"repos/{p['repo']}/rulesets?includes_parents=false", list)
    branch_sets = [r for r in listed if isinstance(r, dict) and r.get("target") == "branch"]
    branch_sets.sort(key=lambda r: r.get("name") != RULESET_NAME)
    for summary in branch_sets:
        full = get(f"repos/{p['repo']}/rulesets/{summary['id']}")
        if covers_default_branch(full, p["branch"]):
            return full
    return None


def rules_by_type(ruleset):
    return {r.get("type"): r.get("parameters") or {} for r in ruleset.get("rules") or [] if isinstance(r, dict)}


def ruleset_shortfalls(ruleset, p):
    """Where the ruleset falls short of the baseline, in plain words."""
    if ruleset is None:
        return [("ruleset", "no ruleset on the default branch")]
    short = []
    if ruleset.get("enforcement") != "active":
        short.append(f"the ruleset's enforcement is {ruleset.get('enforcement')!r}, not 'active'")
    if ruleset.get("bypass_actors"):
        short.append("the ruleset has a bypass list")
    rules = rules_by_type(ruleset)
    for kind in ("deletion", "non_fast_forward", "pull_request", "required_status_checks"):
        if kind not in rules:
            short.append(f"the ruleset has no {kind} rule")
    pr = rules.get("pull_request")
    if pr is not None:
        if not pr.get("require_code_owner_review"):
            short.append("code-owner review is off")
        if not pr.get("dismiss_stale_reviews_on_push"):
            short.append("stale approvals aren't dismissed on a new push")
        if not pr.get("required_review_thread_resolution"):
            short.append("review threads needn't be resolved before merging")
        if not pr.get("require_extra_approval_for_unattributed_changes"):
            short.append("changes by unattributed authors don't need one more approval")
        extra = sorted(set(pr.get("allowed_merge_methods") or ["merge", "squash", "rebase"]) - set(p["methods"]))
        if extra:
            short.append(f"merge methods allowed beyond {p['methods']}: {extra}")
    checks = rules.get("required_status_checks")
    if checks is not None:
        if not checks.get("strict_required_status_checks_policy"):
            short.append("branches needn't be up to date before merging")
        found = {c.get("context"): c.get("integration_id") for c in checks.get("required_status_checks") or []}
        for name in p["all_checks"]:
            if name not in found and name in p["checks"]:
                short.append(f"required check {name!r} is missing")
            elif name not in found:
                short.append(f"required check {name!r} is missing; --apply adds it once it's in "
                             "required_checks_in_ruleset_now, after it has passed on a pull request")
            elif found[name] != ACTIONS_APP:
                short.append(f"required check {name!r} isn't tied to GitHub Actions")
    return [("ruleset", s) for s in short]


def raised_ruleset(ruleset, p):
    """The ruleset to write: the existing one with every shortfall raised, or the baseline's if there's none."""
    base = ruleset or {"name": RULESET_NAME, "target": "branch",
                       "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}}}
    rules = rules_by_type(base)
    pr = dict(rules.get("pull_request") or {})
    pr.setdefault("required_approving_review_count", 0)
    pr.setdefault("require_last_push_approval", False)
    pr["required_review_thread_resolution"] = True
    pr["require_extra_approval_for_unattributed_changes"] = True
    pr["require_code_owner_review"] = True
    pr["dismiss_stale_reviews_on_push"] = True
    kept = [m for m in pr.get("allowed_merge_methods") or [] if m in p["methods"]]
    pr["allowed_merge_methods"] = kept or list(p["methods"])
    checks = dict(rules.get("required_status_checks") or {})
    checks["strict_required_status_checks_policy"] = True
    existing = [dict(c) for c in checks.get("required_status_checks") or []]
    present = {c.get("context") for c in existing}
    wanted = [name for name in p["all_checks"] if name in p["checks"] or name in present]
    listed = [c for c in existing if c.get("context") not in wanted]
    checks["required_status_checks"] = [{"context": name, "integration_id": ACTIONS_APP} for name in wanted] + listed
    rules.update({"deletion": rules.get("deletion") or {}, "non_fast_forward": rules.get("non_fast_forward") or {},
                  "pull_request": pr, "required_status_checks": checks})
    return {
        "name": base.get("name") or RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": base.get("conditions"),
        "rules": [{"type": kind, **({"parameters": params} if params else {})} for kind, params in rules.items()],
    }


# --- the other settings ---------------------------------------------------------------------------------

def actions_shortfalls(p):
    short = []
    perms = get(f"repos/{p['repo']}/actions/permissions")
    if perms.get("enabled") is not True:
        short.append(("actions", "Actions is off, so no required check can run"))
    if not perms.get("sha_pinning_required"):
        short.append(("actions", "Actions may use actions not pinned to a full commit SHA"))
    workflow = get(f"repos/{p['repo']}/actions/permissions/workflow")
    if workflow.get("default_workflow_permissions") != "read":
        short.append(("workflow", "the workflow token isn't read-only by default"))
    if workflow.get("can_approve_pull_request_reviews") is not False:
        short.append(("workflow", "Actions can approve pull requests"))
    return short


def dependabot_shortfalls(p):
    short = []
    if read(f"repos/{p['repo']}/vulnerability-alerts") is None:  # 204 when on, 404 when off
        short.append(("alerts", "Dependabot alerts are off"))
    fixes = read(f"repos/{p['repo']}/automated-security-fixes")  # 404 while alerts are off
    if fixes is not None and not isinstance(fixes, dict):
        raise Unreadable("Dependabot security updates didn't return an object")
    if fixes is None or fixes.get("enabled") is not True:
        short.append(("fixes", "Dependabot security updates are off"))
    return short


def environment_shortfalls(p):
    env = read(f"repos/{p['repo']}/environments/{p['env']}")
    if env is None:
        return [("environment", f"the {p['env']} environment doesn't exist")]
    if not isinstance(env, dict):
        raise Unreadable(f"the {p['env']} environment didn't return an object")
    policy = env.get("deployment_branch_policy") or {}
    if not policy.get("custom_branch_policies") or policy.get("protected_branches"):
        return [("environment", f"the {p['env']} environment isn't limited to named branches")]
    names = get(f"repos/{p['repo']}/environments/{p['env']}/deployment-branch-policies")
    branches = [b.get("name") for b in names.get("branch_policies") or []]
    if branches != [p["branch"]]:
        return [("environment", f"the {p['env']} environment deploys from {branches}, not only {p['branch']!r}")]
    return []


def environment_body(current):
    """The environment to write: limited to named branches, with its reviewers and wait timer carried
    forward, because an update drops the protections it doesn't name."""
    body = {"deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}}
    for rule in (current or {}).get("protection_rules") or []:
        if rule.get("type") == "wait_timer":
            body["wait_timer"] = rule.get("wait_timer")
        elif rule.get("type") == "required_reviewers":
            body["prevent_self_review"] = rule.get("prevent_self_review")
            reviewers = [{"type": r.get("type"), "id": (r.get("reviewer") or {}).get("id")}
                         for r in rule.get("reviewers") or []]
            if not all(r["type"] and r["id"] for r in reviewers):
                raise Unreadable("the deploy environment's reviewers couldn't be read, so they can't be kept")
            body["reviewers"] = reviewers
    return {key: value for key, value in body.items() if value is not None}


# --- check and apply ------------------------------------------------------------------------------------

def shortfalls(p):
    ruleset = find_ruleset(p)
    return ruleset, (ruleset_shortfalls(ruleset, p) + actions_shortfalls(p) + dependabot_shortfalls(p)
                     + environment_shortfalls(p))


def apply(p, ruleset, short):
    """Raise each area that falls short. Nothing here lowers a setting that is already stricter."""
    repo, areas = p["repo"], {area for area, _ in short}
    if "ruleset" in areas:
        body = raised_ruleset(ruleset, p)
        if ruleset:
            put("PUT", f"repos/{repo}/rulesets/{ruleset['id']}", body=body)
        else:
            put("POST", f"repos/{repo}/rulesets", body=body)
    if "actions" in areas:
        perms = get(f"repos/{repo}/actions/permissions")
        put("PUT", f"repos/{repo}/actions/permissions",
            fields=(("-F", "enabled=true"), ("-f", f"allowed_actions={perms.get('allowed_actions') or 'all'}"),
                    ("-F", "sha_pinning_required=true")))
    if "workflow" in areas:
        put("PUT", f"repos/{repo}/actions/permissions/workflow",
            fields=(("-f", "default_workflow_permissions=read"), ("-F", "can_approve_pull_request_reviews=false")))
    if "alerts" in areas:
        put("PUT", f"repos/{repo}/vulnerability-alerts")
    if "fixes" in areas:
        put("PUT", f"repos/{repo}/automated-security-fixes")
    if "environment" in areas:
        env = p["env"]
        put("PUT", f"repos/{repo}/environments/{env}", body=environment_body(read(f"repos/{repo}/environments/{env}")))
        names = get(f"repos/{repo}/environments/{env}/deployment-branch-policies")
        policies = names.get("branch_policies") or []
        for policy in policies:
            if policy.get("name") != p["branch"]:
                put("DELETE", f"repos/{repo}/environments/{env}/deployment-branch-policies/{policy['id']}")
        if p["branch"] not in [policy.get("name") for policy in policies]:
            put("POST", f"repos/{repo}/environments/{env}/deployment-branch-policies",
                fields=(("-f", f"name={p['branch']}"), ("-f", "type=branch")))


def main(argv):
    if argv not in ([], ["--apply"]):
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: github_settings.py [--apply]", file=sys.stderr)
        return 2
    try:
        p = project()
        ruleset, short = shortfalls(p)
        if short and argv == ["--apply"]:
            print("Raising to the baseline:")
            for _, s in short:
                print(f"  - {s}")
            apply(p, ruleset, short)
            ruleset, short = shortfalls(p)
    except Unreadable as exc:
        print(f"Couldn't check the GitHub settings: {exc}", file=sys.stderr)
        return 2
    if short:
        print(f"{p['repo']}: {len(short)} setting(s) fall short of the baseline:")
        for _, s in short:
            print(f"  - {s}")
        return 1
    print(f"{p['repo']}: every GitHub setting is at the baseline or stricter.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
