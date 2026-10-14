"""The starter only: a pull request into the starter must carry none of the source repository's
own settings or lowerings, and must keep the placeholders an adopter fills in. It reads the files
as data and runs nothing from them. Each marker is built from two parts, so this file matches
neither itself nor the release's own leak check. The source's private names aren't checked here:
that list can't be public, so the release's local check covers them.
"""

import json
import os
import re
import sys

# The switches that let sessions change enforcement, and their guard code; the inventory's
# lowering clause; the wording for those switches; and the Checkov findings a project accepted:
# the source's own lowerings, which the starter never carries.
PARTS = (
    ("sessions_", "change_enforcement"),
    ("session_", "lowered"),
    ("GUARD_", "SELF"),
    ("session ", "switch"),
    ("Lowered ", "here"),
    ("checkov/accepted", ".json"),
)
MARKERS = [first + second for first, second in PARTS]
GUID = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", re.IGNORECASE)
STACK = ".claude/security-stack.json"
STATUS = ".claude/security-status.json"
problems = []


def load(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def entries(text):
    """The lines that aren't blank or a comment."""
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


# Every file of the checkout, as a path relative to it with forward slashes; git's own folder aside.
files = []
for folder, subfolders, names in os.walk("."):
    subfolders[:] = [sub for sub in subfolders if sub != ".git"]
    files += [os.path.relpath(os.path.join(folder, name)).replace(os.sep, "/") for name in names]
files.sort()
if not files:
    sys.exit("starter check: no files to check")
owner = (os.environ.get("GITHUB_REPOSITORY_OWNER") or "").lower()
for name in files:
    try:
        text = load(name)
    except (UnicodeDecodeError, OSError):
        continue  # a binary file
    problems += [f"{name}: the source's lowering '{m}'" for m in MARKERS if m in text]
    config = name.startswith((".claude/", ".github/")) and name.endswith((".json", ".yml", ".yaml"))
    if config and GUID.search(text):
        problems.append(f"{name}: a GUID, such as a tenant, subscription or client ID")
    if owner and name != "LICENSE" and owner in text.lower():
        problems.append(f"{name}: the repository owner's handle, which belongs only in LICENSE")

stack = json.loads(load(STACK))
github = stack.get("github") or {}
if github.get("repository") != "OWNER/REPOSITORY":
    problems.append(f"{STACK}: repository is {github.get('repository')!r}, not OWNER/REPOSITORY")
for key in ("azure", "claude"):
    if key in stack:
        problems.append(f"{STACK}: a '{key}' section, which the starter never has")
if github.get("dependabot_merges_on_green"):
    problems.append(f"{STACK}: Dependabot's merge-on-green lowering is on")
owners = {word for line in entries(load(".github/CODEOWNERS")) for word in line.split()[1:]}
if owners != {"@OWNER"}:
    problems.append(f".github/CODEOWNERS: owners {sorted(owners)}, expected only @OWNER")
if entries(load(".github/blocked-terms.txt")):
    problems.append(".github/blocked-terms.txt: entries; the starter ships the list empty")
if os.path.exists(STATUS):
    status = json.loads(load(STATUS))
    if status.get("done_and_verified") or status.get("open_owner"):
        problems.append(f"{STATUS}: a project's own status; the starter ships it fresh")

for problem in problems:
    print(f"::error::{problem}")
if problems:
    sys.exit(f"starter check: {len(problems)} problem(s)")
print(f"starter check: clean ({len(files)} files)")
