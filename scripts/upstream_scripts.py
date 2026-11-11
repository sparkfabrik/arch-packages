#!/usr/bin/env python3
"""Compare upstream install scripts with the copies reviewed for our recipes.

Upstream scripts are data here: they are downloaded and compared, never run.
"""
import argparse
import difflib
import hashlib
import os
from pathlib import Path
import re
import sys
import tomllib
import urllib.request

CONFIG = Path("upstream-scripts.toml")
MAX_BYTES = 1 << 20
MAX_MARKDOWN = 60000


def entries(text):
    """Package name -> upstream script URL, from upstream-scripts.toml."""
    config = tomllib.loads(text)
    result = {}
    for name, entry in config.items():
        if not re.fullmatch(r"[a-z0-9][a-z0-9+._-]*", name):
            raise ValueError(f"Invalid package name: {name!r}")
        if not isinstance(entry, dict) or set(entry) != {"url"} or not isinstance(entry["url"], str):
            raise ValueError(f"{name}: expected exactly one url")
        if not re.fullmatch(r"https://[^\s?#]+", entry["url"]):
            raise ValueError(f"{name}: the url must be a plain HTTPS URL")
        result[name] = entry["url"]
    return result


def reviewed_path(package):
    return Path("packages") / package / "upstream-install.reviewed.sh"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "sparkfabrik-arch-packages/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"{url} is larger than {MAX_BYTES} bytes")
    return data


def unified_diff(package, url, reviewed, current):
    """The diff from the reviewed copy to the current script; empty when the bytes match."""
    if reviewed == current:
        return ""
    old = reviewed.decode("utf-8", "replace").splitlines(keepends=True)
    new = current.decode("utf-8", "replace").splitlines(keepends=True)
    diff = "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
                   for line in difflib.unified_diff(old, new, f"a/{reviewed_path(package)}", f"b/{url}"))
    # Bytes that differ without a visible text change, such as invalid UTF-8.
    return diff or f"Binary difference between {reviewed_path(package)} and {url}\n"


def markdown(package, url, diff):
    """A PR body section; the fence is longer than any backtick run in the diff."""
    if len(diff) > MAX_MARKDOWN:
        diff = diff[:MAX_MARKDOWN] + "\n[diff truncated; run the comparison locally]\n"
    longest = max((len(run) for run in re.findall(r"`+", diff)), default=0)
    fence = "`" * max(3, longest + 1)
    return (f"**The upstream install script for `{package}` changed since its last review.** "
            f"Review it before merging, as `CONTRIBUTING.md` describes. Source: {url}\n\n"
            f"{fence}diff\n{diff}{'' if diff.endswith(chr(10)) else chr(10)}{fence}\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="diff the reviewed copies against upstream; exit 1 on a change")
    check.add_argument("packages", nargs="*", help="default: every package in upstream-scripts.toml")
    check.add_argument("--allow-unlisted", action="store_true", help="skip packages without a reviewed script")
    check.add_argument("--markdown", type=Path, help="write a PR body section for changed scripts")
    accept = commands.add_parser("accept", help="replace the reviewed copy with the upstream script you reviewed")
    accept.add_argument("package")
    accept.add_argument("--sha256", required=True, type=str.lower,
                        help="SHA256 of the script you reviewed, as printed by check")
    args = parser.parse_args(argv)

    urls = entries(CONFIG.read_text())
    if args.command == "accept":
        if args.package not in urls:
            raise SystemExit(f"{args.package} has no entry in {CONFIG}")
        if not re.fullmatch(r"[0-9a-f]{64}", args.sha256):
            raise SystemExit("--sha256 must be 64 hexadecimal characters")
        current = fetch(urls[args.package])
        digest = hashlib.sha256(current).hexdigest()
        if digest != args.sha256:
            raise SystemExit(f"{urls[args.package]} now has sha256 {digest}, not the reviewed {args.sha256}; "
                             "nothing was written. Compare and review again.")
        path = reviewed_path(args.package)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(current)
        print(f"{path}: sha256 {digest}")
        return 0

    packages = args.packages or sorted(urls)
    unknown = [name for name in packages if name not in urls]
    if unknown and not args.allow_unlisted:
        raise SystemExit(f"No reviewed script for: {', '.join(unknown)}")
    sections = []
    for package in packages:
        if package not in urls:
            print(f"{package}: no reviewed script", file=sys.stderr)
            continue
        current = fetch(urls[package])
        diff = unified_diff(package, urls[package], reviewed_path(package).read_bytes(), current)
        if diff:
            print(diff, end="")
            print(f"{package}: upstream sha256 {hashlib.sha256(current).hexdigest()}", file=sys.stderr)
            sections.append(markdown(package, urls[package], diff))
        else:
            print(f"{package}: matches the reviewed copy", file=sys.stderr)
    if args.markdown and sections:
        args.markdown.write_text("\n".join(sections))
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.write(f"changed={'true' if sections else 'false'}\n")
    return 1 if sections else 0


if __name__ == "__main__":
    sys.exit(main())
