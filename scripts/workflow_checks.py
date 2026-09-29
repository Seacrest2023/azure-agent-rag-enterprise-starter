#!/usr/bin/env python3
"""Structural checks on a pull request's changed workflow files, for the security gate.

  workflow_checks.py --root DIR --trusted PATH --required NAME [--required NAME ...] FILE...

Each FILE is a repository path of a changed workflow; the PR's copy is DIR/FILE.

The trusted workflow (PATH: the one that produces the required checks, which
pull_request_target runs from the default branch) must keep the properties
that make those checks trustworthy:
  - its only trigger is pull_request_target, with opened, synchronize, reopened
    and edited, and it declares workflow permissions no broader than read
  - each required check name is produced by exactly one job
  - a required job has no `if:`, `needs:` or `continue-on-error`, and neither
    do its steps: a skipped required check counts as passed, and
    continue-on-error turns a failure into a pass
  - a required job asks for no write permission
  - a required job that checks out the PR's code does it without persisted
    credentials and passes no token or secret to any step

Every other workflow must not produce a required check name, including through
a job name built from an expression that could evaluate to one.

Exit 0: no findings. Exit 1: findings, one per line. Exit 2: couldn't check.
"""

import argparse
import os
import re
import sys

import yaml

EXPRESSION = re.compile(r"\$\{\{.*?\}\}", re.DOTALL)
# The only expressions a job that runs PR code may use. Anything else (secrets,
# the token in any syntax such as github['token'], toJSON(github), ...) could
# hand a credential to PR code, so it is refused rather than pattern-matched.
SAFE_EXPRESSION = re.compile(
    r"github\.(event\.pull_request\.(number|head\.sha|base\.sha|head\.repo\.full_name|changed_files|commits)"
    r"|workspace|repository)")
TOKEN_NAMED = re.compile(r"^(GH_TOKEN|GITHUB_TOKEN)$", re.IGNORECASE)
REQUIRED_TYPES = {"opened", "synchronize", "reopened", "edited"}
PR_REF = re.compile(r"refs/pull/|pull_request\.head\.|github\.head_ref")


def triggers(doc):
    on = doc.get("on", doc.get(True))  # YAML 1.1 reads a bare `on` key as true
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {t: None for t in on}
    return on if isinstance(on, dict) else {}


def writes(permissions):
    if permissions is None:
        return False
    levels = [permissions] if isinstance(permissions, str) else list(permissions.values()) \
        if isinstance(permissions, dict) else ["?"]
    return any(not isinstance(level, str) or "write" in level or level == "?" for level in levels)


def strings(obj):
    """Every key and string value in a nested structure."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            yield from strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from strings(value)
    elif isinstance(obj, str):
        yield obj


def job_name(job_id, job):
    return str(job.get("name", job_id)) if isinstance(job, dict) else job_id


def could_be(name, required):
    """Whether a job name, possibly containing ${{ }} expressions, can equal a required name."""
    if not EXPRESSION.search(name):
        return name in required
    literal_parts = EXPRESSION.split(name)
    pattern = re.compile(".*".join(re.escape(p) for p in literal_parts), re.DOTALL)
    return any(pattern.fullmatch(r) for r in required)


def check_trusted(path, doc, required, findings):
    on = triggers(doc)
    if set(on) != {"pull_request_target"}:
        findings.append(f"{path}: the trigger must be pull_request_target only (found: {', '.join(map(str, on)) or 'none'})")
    else:
        types = (on["pull_request_target"] or {}).get("types") if isinstance(on["pull_request_target"], (dict, type(None))) else None
        missing = REQUIRED_TYPES - set(types or [])
        if missing:
            findings.append(f"{path}: pull_request_target must include types {', '.join(sorted(missing))}")
    if "permissions" not in doc or writes(doc.get("permissions")):
        findings.append(f"{path}: workflow permissions must be declared and read-only")

    jobs = doc.get("jobs") or {}
    for name in sorted(required):
        producers = [jid for jid, job in jobs.items() if could_be(job_name(jid, job), {name})]
        if len(producers) != 1:
            findings.append(f"{path}: required check '{name}' must come from exactly one job (found {len(producers)})")
            continue
        job = jobs[producers[0]]
        where = f"{path}: job '{name}'"
        for key in ("if", "needs"):
            if key in job:
                findings.append(f"{where} has `{key}:`; a skipped required check counts as passed")
        if job.get("continue-on-error", False) is not False:
            findings.append(f"{where} has continue-on-error, which turns a failure into a pass")
        if writes(job.get("permissions")):
            findings.append(f"{where} asks for write permission")
        steps = job.get("steps") or []
        runs_pr_code = False
        for i, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                continue
            if "if" in step:
                findings.append(f"{where}, step {i} has `if:`; a skipped check step lets the job pass")
            if step.get("continue-on-error", False) is not False:
                findings.append(f"{where}, step {i} has continue-on-error, which turns a failure into a pass")
            uses = str(step.get("uses", ""))
            with_ = step.get("with") or {}
            if uses.startswith("actions/checkout@") and PR_REF.search(str(with_.get("ref", ""))):
                runs_pr_code = True
                if str(with_.get("persist-credentials", "")).lower() != "false":
                    findings.append(f"{where}, step {i} checks out the PR without persist-credentials: false")
        if runs_pr_code:
            for text in strings(job):
                if TOKEN_NAMED.match(text):
                    findings.append(f"{where} runs the PR's code and sets {text}")
                for expr in EXPRESSION.findall(text):
                    inner = expr[3:-2].strip()
                    if not SAFE_EXPRESSION.fullmatch(inner):
                        findings.append(f"{where} runs the PR's code and uses an expression outside the safe list: {expr}")


def check_other(path, doc, required, findings):
    for jid, job in (doc.get("jobs") or {}).items():
        name = job_name(jid, job)
        if could_be(name, required):
            findings.append(f"{path}: job '{name}' could report a required check name; only the trusted workflow may")


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--trusted", required=True)
    parser.add_argument("--required", action="append", default=[])
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    required = {r for r in args.required if r}
    if not required:
        raise ValueError("no required check names given")
    findings = []
    for path in args.files:
        with open(os.path.join(args.root, path), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        if not isinstance(doc, dict):
            findings.append(f"{path}: not a workflow")
            continue
        (check_trusted if path == args.trusted else check_other)(path, doc, required, findings)
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as exc:  # never let a parse failure read as "no findings"
        print(f"workflow_checks: {exc}", file=sys.stderr)
        sys.exit(2)
