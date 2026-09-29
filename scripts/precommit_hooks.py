#!/usr/bin/env python3
"""Print a .pre-commit-config.yaml (on stdin) as one line per protected entry.

Used by the security gate to refuse PRs that weaken the pre-commit chain: an
entry in the base branch's output that is missing from the PR's means a hook
was removed or its definition changed (for example `stages: [manual]` added,
`files` narrowed, `exclude` widened, args or entry changed). Adding hooks is
allowed, and so is bumping a remote repository's `rev`, which is left out.

The global settings that can narrow what runs are always printed, with their
defaults, so adding a global `exclude` or `files` where there was none also
shows up as a change. Settings that can only make hooks fail, not skip
(fail_fast, minimum_pre_commit_version, default_language_version), aren't
protected, so ordinary maintenance of them isn't blocked.

With --pins, it prints instead each hook repository whose rev isn't a full
commit hash, as "repo<TAB>rev". A full hash names one commit; a tag, branch or
short hash is looked up by name, so the repository's owner can move it. The
local and meta repositories have no rev.

Exit 2 if the input isn't a valid config, so the caller fails closed.
"""

import json
import re
import sys

import yaml

FULL_HASH = re.compile(r"[0-9a-f]{40}")

GLOBAL_DEFAULTS = {
    "files": "",
    "exclude": "^$",
    "default_stages": None,
    "default_install_hook_types": ["pre-commit"],  # narrowing it stops `pre-commit install` installing hooks
}


def main():
    # LF on every platform: on Windows, a CR the shell strips from the last line only makes equal entries differ.
    sys.stdout.reconfigure(newline="\n")
    config = yaml.safe_load(sys.stdin.read())
    if not isinstance(config, dict) or not isinstance(config.get("repos"), list):
        raise ValueError("not a pre-commit config")
    if sys.argv[1:] == ["--pins"]:
        for repo in config["repos"]:
            url, rev = repo["repo"], repo.get("rev")
            if url not in ("local", "meta") and not (isinstance(rev, str) and FULL_HASH.fullmatch(rev)):
                print(f"{url}\t{rev}")
        return
    for key, default in GLOBAL_DEFAULTS.items():
        print(f"global\t{key}\t{json.dumps(config.get(key, default), sort_keys=True)}")
    for repo in config["repos"]:
        url = repo["repo"]
        for hook in repo.get("hooks", []):
            print(f"hook\t{url}\t{hook['id']}\t{json.dumps(hook, sort_keys=True)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never let a parse failure read as "no hooks"
        print(f"precommit_hooks: {exc}", file=sys.stderr)
        sys.exit(2)
