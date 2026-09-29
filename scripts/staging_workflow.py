#!/usr/bin/env python3
"""Write a throwaway pull_request copy of the trusted workflow, to test it on GitHub.

  staging_workflow.py [SRC] [DST]
  (defaults: .github/workflows/security-gate.yml -> .github/workflows/staging-check.yml)

pull_request_target always runs the default branch's workflow file, so a
change to the trusted workflow can't be tried on a pull request before it
merges. This copy differs only in its trigger (pull_request) and its job and
check names (suffixed -staging), so it runs the new jobs, on GitHub's runners,
on a throwaway PR. See docs/security-setup-prompt.md, Phase 3. Never merge the
copy: under pull_request, a PR controls its steps.
"""

import re
import sys

REQUIRED_JOBS = ("security-critical-gate", "secret-scan", "precommit", "selftest", "python")


def main(argv):
    src = argv[0] if argv else ".github/workflows/security-gate.yml"
    dst = argv[1] if len(argv) > 1 else ".github/workflows/staging-check.yml"
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    start, end = text.index("\non:"), text.index("\npermissions:")
    text = text[:start] + "\non:\n  pull_request:\n" + text[end:]
    text = re.sub(r"^name: .*$", "name: staging-check", text, count=1, flags=re.M)
    text = text.replace("group: security-gate-", "group: staging-check-")
    for job in REQUIRED_JOBS:
        text = text.replace(f"    name: {job}\n", f"    name: {job}-staging\n")
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# THROWAWAY: a pull_request copy of the trusted workflow, to test it before it\n"
                 "# reaches the default branch (scripts/staging_workflow.py). Never merge this file.\n")
        fh.write(text)
    print(f"Wrote {dst}")


if __name__ == "__main__":
    main(sys.argv[1:])
