#!/usr/bin/env python3
"""Fail namcap errors and warnings without an exact, documented exception."""
import ast
import pathlib
import re
import subprocess
import sys

def normalize(line):
    # Namcap prints dependency file sets in a different order between processes.
    match = re.search(r"\(needed in files (\[.*\])\)$", line)
    if match:
        line = line[:match.start(1)] + repr(sorted(ast.literal_eval(match[1]))) + ")"
    return line


def main():
    allow_file = pathlib.Path(sys.argv[1])
    allowed = set()
    if allow_file.exists():
        allowed = {line for line in allow_file.read_text().splitlines() if line and not line.startswith("#")}
    failed = False
    accepted = 0
    for target in sys.argv[2:]:
        result = subprocess.run(["namcap", target], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        failed |= result.returncode != 0
        for line in result.stdout.splitlines():
            if " E: " in line or (" W: " in line and normalize(line) not in allowed):
                failed = True
                print(line)
            elif " W: " in line:
                accepted += 1
            else:
                print(line)
    print(f"Namcap: {accepted} documented upstream warnings; {'FAILED' if failed else 'passed'}")
    sys.exit(int(failed))


if __name__ == "__main__":
    main()
