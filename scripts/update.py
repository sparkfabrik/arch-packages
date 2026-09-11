#!/usr/bin/env python3
"""Prepare a reviewed version bump; upstream text never becomes shell code."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib


def upstream_version(output, package="chatgpt-desktop"):
    records = [json.loads(line) for line in output.splitlines() if line.strip()]
    versions = {record["version"] for record in records if record.get("name") == package and "version" in record}
    if len(versions) != 1:
        raise ValueError(f"Expected exactly one upstream version for {package}")
    version = versions.pop()
    if not re.fullmatch(r"[0-9][a-zA-Z0-9._+]*", version):
        raise ValueError("Invalid upstream version")
    return version


def main():
    config = tomllib.loads(Path("nvchecker.toml").read_text())
    packages = sorted(name for name in config if not name.startswith("__"))
    if any(not re.fullmatch(r"[a-z0-9][a-z0-9+._-]*", name) for name in packages):
        raise ValueError("Invalid nvchecker package name")
    if sys.argv[1:] == ["--list"]:
        print(json.dumps(packages))
        return
    package = sys.argv[1]
    if package not in packages:
        raise ValueError("Package has no nvchecker entry")
    output = subprocess.check_output(["nvchecker", "--failures", "--logger", "json", "--entry", package, "-c", "nvchecker.toml"], text=True)
    version = upstream_version(output, package)
    source = Path("packages") / package
    recipe = (source / "PKGBUILD").read_text()
    current = re.search(r"(?m)^pkgver=(.+)$", recipe)[1]
    if int(subprocess.check_output(["vercmp", version, current], text=True)) <= 0:
        print(f"Already current: {current}", file=sys.stderr)
        return
    destination = Path(".build/update") / package
    shutil.copytree(source, destination, dirs_exist_ok=True)
    recipe = re.sub(r"(?m)^pkgver=.+$", f"pkgver={version}", recipe)
    recipe = re.sub(r"(?m)^pkgrel=.+$", "pkgrel=1", recipe)
    (destination / "PKGBUILD").write_text(recipe)
    subprocess.run(["id", "builder"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["chown", "-R", "builder:builder", str(destination)], check=True)
    subprocess.run(["runuser", "-u", "builder", "--", "updpkgsums"], cwd=destination, check=True, stdout=sys.stderr)
    info = subprocess.check_output(["runuser", "-u", "builder", "--", "makepkg", "--printsrcinfo"], cwd=destination, text=True)
    shutil.copyfile(destination / "PKGBUILD", source / "PKGBUILD")
    (source / ".SRCINFO").write_text(info)
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.write(f"version={version}\n")
    print(f"Prepared {version}", file=sys.stderr)


if __name__ == "__main__":
    main()
