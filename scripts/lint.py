#!/usr/bin/env python3
"""Fail namcap errors and warnings without a reviewed exact or star-pattern exception."""
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
    exact = {line for line in allowed if "*" not in line}
    patterns = [re.compile(re.escape(line).replace(r"\*", ".*")) for line in allowed if "*" in line]
    failed = False
    total = matched_exact = matched_patterns = 0
    for target in sys.argv[2:]:
        result = subprocess.run(["namcap", target], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        failed |= result.returncode != 0
        for line in result.stdout.splitlines():
            if " E: " in line:
                failed = True
                print(line)
            elif " W: " in line:
                total += 1
                normalized = normalize(line)
                if normalized in exact:
                    matched_exact += 1
                elif any(pattern.fullmatch(normalized) for pattern in patterns):
                    matched_patterns += 1
                else:
                    failed = True
                    print(line)
            else:
                print(line)
    print(f"Namcap: {total} warnings; {matched_exact} matched exact; {matched_patterns} matched patterns; {'FAILED' if failed else 'passed'}")
    sys.exit(int(failed))


if __name__ == "__main__":
    main()
