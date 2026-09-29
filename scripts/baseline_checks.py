#!/usr/bin/env python3
"""Compare the PR's .secrets.baseline with the base branch's, for the security gate.

  baseline_checks.py BASE_FILE HEAD_FILE      (an empty BASE_FILE means the PR adds it)

detect-secrets takes its detectors and filters from the baseline, so the
baseline can switch scanning off as surely as a missing hook can. The PR's
copy may make scanning stricter, never looser:
  - detectors (plugins_used): none removed and none changed (e.g. a raised
    entropy limit); new detectors are fine
  - filters (filters_used): no new custom filter and no new pattern in an
    existing one; removing patterns is fine. detect-secrets' own heuristic
    filters, which take no settings, may be added (new releases add them)
  - allowlisted findings (results): none added, compared by file, detector
    type and hashed secret, so a swap can't hide behind an equal count

Exit 0: no findings. Exit 1: findings, one per line. Exit 2: couldn't check.
"""

import json
import sys

BUILT_IN_HEURISTICS = "detect_secrets.filters.heuristic."


def load(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    doc = json.loads(text) if text.strip() else {}
    if not isinstance(doc, dict):
        raise ValueError(f"{path} is not a detect-secrets baseline")
    return doc


def canonical(obj):
    return json.dumps(obj, sort_keys=True)


def main(argv):
    base, head = load(argv[0]), load(argv[1])
    findings = []

    head_plugins = {canonical(p) for p in head.get("plugins_used", [])}
    for plugin in base.get("plugins_used", []):
        if canonical(plugin) not in head_plugins:
            findings.append(f"detector removed or changed: {plugin.get('name', canonical(plugin))}")

    base_filters = {f.get("path"): f for f in base.get("filters_used", [])}
    for flt in head.get("filters_used", []):
        path = flt.get("path", "")
        old = base_filters.get(path)
        if old is None:
            if not (set(flt) == {"path"} and path.startswith(BUILT_IN_HEURISTICS)):
                findings.append(f"filter added: {canonical(flt)}")
            continue
        for key, value in flt.items():
            if key == "path":
                continue
            before = old.get(key)
            if isinstance(value, list) and isinstance(before, list):
                added = [v for v in value if v not in before]
                if added:
                    findings.append(f"filter {path}: {key} gained {canonical(added)}")
            elif value != before:
                findings.append(f"filter {path}: {key} changed from {canonical(before)} to {canonical(value)}")

    def entries(doc):
        return {
            (filename, item.get("type"), item.get("hashed_secret"))
            for filename, items in (doc.get("results") or {}).items()
            for item in items
        }

    for filename, kind, _ in sorted(entries(head) - entries(base)):
        findings.append(f"allowlist entry added: {filename} ({kind})")

    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as exc:  # never let a parse failure read as "nothing changed"
        print(f"baseline_checks: {exc}", file=sys.stderr)
        sys.exit(2)
