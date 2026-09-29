#!/usr/bin/env python3
"""Block names that must never appear in this repository.

The terms themselves are never stored. The list (default
.github/blocked-terms.txt, or $BLOCKED_TERMS_FILE) holds one line per term:

  <length> <sha256>          blocked everywhere: file contents, paths, PR text, commits
  <length> <sha256> paths    blocked in file and folder names only

Text is lowercased and stripped to letters and digits, then every window of
each listed length is hashed and compared, so a term is caught whatever its
case or separators ("Acme Corp", "acme-corp", "AcmeCorp", "acme.corp").

Usage:
  check_blocked_terms.py --stdin LABEL          scan text on stdin
  check_blocked_terms.py --stdin-paths LABEL    scan file paths on stdin (both scopes)
  check_blocked_terms.py FILE...                scan files and their paths
  check_blocked_terms.py --message FILE         scan a commit message's text (the commit-msg hook)
  check_blocked_terms.py --add [--paths] TERM...  add terms to the list

Findings name the place and line, never the matched text.
Exit 0: clean. Exit 1: a blocked name was found. Exit 2: the check could not run.
"""

import hashlib
import os
import re
import sys

DEFAULT_LIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".github", "blocked-terms.txt")
NON_ALNUM = re.compile(r"[^a-z0-9]")
MIN_LENGTH = 4
SCOPES = ("everywhere", "paths")


def list_path():
    return os.environ.get("BLOCKED_TERMS_FILE") or DEFAULT_LIST


def normalise(text):
    return NON_ALNUM.sub("", text.lower())


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def load():
    """Return {scope: {length: {hash}}}."""
    terms = {scope: {} for scope in SCOPES}
    with open(list_path(), encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            fields = line.split()
            if not fields or fields[0].startswith("#"):
                continue
            if len(fields) not in (2, 3) or (len(fields) == 3 and fields[2] != "paths"):
                raise SystemExit(f"{list_path()}:{n}: expected '<length> <sha256> [paths]'; refusing to pass.")
            scope = "paths" if len(fields) == 3 else "everywhere"
            terms[scope].setdefault(int(fields[0]), set()).add(fields[1])
    if not any(terms.values()):
        raise SystemExit(f"{list_path()} lists no terms; refusing to pass.")
    return terms


def has_term(text, table):
    text = normalise(text)
    return any(
        digest(text[start:start + length]) in hashes
        for length, hashes in table.items()
        for start in range(len(text) - length + 1)
    )


def path_table(terms):
    merged = {}
    for scope in SCOPES:
        for length, hashes in terms[scope].items():
            merged.setdefault(length, set()).update(hashes)
    return merged


def scan(label, lines, table, what="blocked name", across_lines=True):
    """Report each line where a term starts. With across_lines, the text is
    normalised as one string, so a term split over a line break still matches."""
    if not across_lines:
        found = [n for n, line in enumerate(lines, 1) if has_term(line, table)]
    else:
        text, line_of = [], []
        for n, line in enumerate(lines, 1):
            norm = normalise(line)
            text.append(norm)
            line_of.extend([n] * len(norm))
        text = "".join(text)
        found = sorted({
            line_of[start]
            for length, hashes in table.items()
            for start in range(len(text) - length + 1)
            if digest(text[start:start + length]) in hashes
        })
    for n in found:
        print(f"{label}:{n}: {what}")
    return bool(found)


def add(args):
    scope = ""
    if args[:1] == ["--paths"]:
        scope, args = " paths", args[1:]
    with open(list_path(), "a", encoding="utf-8", newline="\n") as fh:
        for term in args:
            norm = normalise(term)
            if len(norm) < MIN_LENGTH:
                raise SystemExit(f"Terms need at least {MIN_LENGTH} letters or digits, or they'd match ordinary words.")
            fh.write(f"{len(norm)} {digest(norm)}{scope}\n")
    print(f"Added {len(args)} term(s).")


def read_stdin():
    # Bytes, decoded leniently: binary files (images, archives) must scan, not crash.
    return sys.stdin.buffer.read().decode("utf-8", errors="replace").splitlines()


def main(argv):
    if argv[:1] == ["--add"]:
        add(argv[1:])
        return 0
    terms = load()
    label = argv[1] if len(argv) > 1 else "stdin"
    if argv[:1] == ["--stdin"]:
        return 1 if scan(label, read_stdin(), terms["everywhere"]) else 0
    if argv[:1] == ["--stdin-paths"]:
        # One path per line: joining paths would invent names across them.
        return 1 if scan(label, read_stdin(), path_table(terms), "blocked name in a path", across_lines=False) else 0
    if argv[:1] == ["--message"]:
        # The text only: git chooses where the message file lives (for a worktree,
        # inside the main clone's .git), so that path isn't part of the commit.
        with open(argv[1], encoding="utf-8", errors="replace") as fh:
            return 1 if scan("commit message", fh.read().splitlines(), terms["everywhere"]) else 0
    failed = False
    for path in argv:
        if has_term(path, path_table(terms)):
            print(f"{path}: blocked name in a path")
            failed = True
        with open(path, encoding="utf-8", errors="replace") as fh:
            failed |= scan(path, fh.read().splitlines(), terms["everywhere"])
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit as exc:
        if isinstance(exc.code, str):  # a refusal message, not a result
            print(exc.code, file=sys.stderr)
            sys.exit(2)
        raise
    except Exception as exc:  # never let a crash read as "no names found"
        print(f"check_blocked_terms: {exc}", file=sys.stderr)
        sys.exit(2)
