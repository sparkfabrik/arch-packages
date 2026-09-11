#!/usr/bin/env python3
"""Merge only App-authored, allowlisted version bumps after required CI passes."""
import json
import os
from pathlib import Path
import re
import subprocess


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def validate_bump(old, new, old_info, new_info):
    for text in [old, new]:
        for variable in ["pkgver", "pkgrel", "sha256sums_x86_64"]:
            if len(re.findall(rf"(?m)^{variable}=", text)) != 1:
                raise ValueError("Duplicate or missing assignments require human review")
    pattern = r"(?m)^pkgver=([0-9]+(?:\.[0-9]+)+)$"
    previous = re.search(pattern, old)
    current = re.search(pattern, new)
    if not previous or not current or tuple(map(int, current[1].split("."))) <= tuple(map(int, previous[1].split("."))):
        raise ValueError("Auto-merge requires a newer numeric upstream version")
    if not re.search(r"(?m)^pkgrel=1$", new):
        raise ValueError("Upstream bumps must reset pkgrel to 1")
    checksum_pattern = r"(?m)^sha256sums_x86_64=\('([a-f0-9]{64})'\)$"
    old_sum = re.search(checksum_pattern, old)
    new_sum = re.search(checksum_pattern, new)
    if not old_sum or not new_sum:
        raise ValueError("Auto-merge requires one pinned x86_64 SHA256 checksum")
    normalize = lambda text: re.sub(checksum_pattern, "sha256sums_x86_64=()", re.sub(r"(?m)^pkg(?:ver|rel)=.*$", "", text))
    if normalize(old) != normalize(new):
        raise ValueError("Changes beyond pkgver, pkgrel and checksum require human review")
    expected = old_info.replace(previous[1], current[1]).replace(old_sum[1], new_sum[1])
    expected = re.sub(r"(?m)^(\s*pkgrel = ).+$", r"\g<1>1", expected)
    if expected != new_info:
        raise ValueError("Unexpected .SRCINFO changes require human review")


def main():
    head = os.environ["HEAD_SHA"]
    branch = os.environ["HEAD_BRANCH"]
    if not re.fullmatch(r"[0-9a-f]{40}", head) or not branch.startswith("chore/update-"):
        return
    prs = json.loads(run("gh", "pr", "list", "--state", "open", "--head", branch,
                         "--json", "number,headRefOid,isCrossRepository,baseRefName,author,isDraft,mergeStateStatus"))
    for pr in prs:
        if pr["headRefOid"] != head or pr["baseRefName"] != "main" or pr["isDraft"]:
            continue
        if not pr["author"].get("is_bot") or pr["author"]["login"] != "app/sparkfabrik-pr-automation":
            continue
        if pr["isCrossRepository"]:
            continue
        run("git", "fetch", "origin", "main", head)
        base = run("git", "merge-base", "origin/main", head)
        changed = run("git", "diff", "--name-only", base, head).splitlines()
        names = Path(".github/auto-merge-packages").read_text().splitlines()
        package = next((name for name in names if set(changed) == {f"packages/{name}/PKGBUILD", f"packages/{name}/.SRCINFO"}), None)
        if not package:
            print("No allowlisted version-only change; human review required")
            continue
        contents = []
        for path in [f"packages/{package}/PKGBUILD", f"packages/{package}/.SRCINFO"]:
            for revision in [base, head]:
                if not run("git", "ls-tree", revision, "--", path).startswith("100644 blob "):
                    raise ValueError("Auto-merge accepts only regular recipe files")
                contents.append(run("git", "show", f"{revision}:{path}"))
        validate_bump(*contents)
        number = str(pr["number"])
        if pr["mergeStateStatus"] == "BEHIND":
            run("gh", "api", "--method", "PUT", f"repos/{os.environ['GH_REPO']}/pulls/{number}/update-branch", "-f", f"expected_head_sha={head}")
            print("Updated branch; waiting for fresh CI")
            continue
        checks = json.loads(subprocess.check_output(
            ["gh", "pr", "checks", number, "--required", "--json", "name,state"], text=True,
            env={**os.environ, "GH_TOKEN": os.environ["CHECKS_TOKEN"]}))
        if not checks or any(check["state"] != "SUCCESS" for check in checks):
            print("Required checks are not all successful")
            continue
        # Merge now, never leave auto-merge enabled for a subsequently edited head.
        result = subprocess.run(["gh", "pr", "merge", number, "--squash", "--match-head-commit", head], text=True, capture_output=True)
        if result.returncode:
            # Another package may have merged after we read the branch status.
            status = run("gh", "pr", "view", number, "--json", "mergeStateStatus", "--jq", ".mergeStateStatus")
            if status != "BEHIND":
                raise RuntimeError(result.stderr)
            run("gh", "api", "--method", "PUT", f"repos/{os.environ['GH_REPO']}/pulls/{number}/update-branch", "-f", f"expected_head_sha={head}")


if __name__ == "__main__":
    main()
