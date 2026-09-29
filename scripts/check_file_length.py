"""Fails when an application source file passes 500 lines. Tests are exempt.

Pre-commit passes the staged files under src/. Long files are where wiring
problems hide: split one by responsibility rather than trimming lines.
"""

import sys

LIMIT = 500


def main(paths: list[str]) -> int:
    too_long = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            count = sum(1 for _ in fh)
        if count > LIMIT:
            too_long.append(f"{path}: {count} lines (limit {LIMIT}); split it by responsibility")
    for line in too_long:
        print(line)
    return 1 if too_long else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
