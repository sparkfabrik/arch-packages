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
import urllib.request


def openai_deb_checksum(index, version):
    checksums = set()
    for paragraph in re.split(r"\n\s*\n", index.replace("\r\n", "\n").strip()):
        fields = {}
        for line in paragraph.splitlines():
            if line.startswith((" ", "\t")) or ": " not in line:
                continue
            key, value = line.split(": ", 1)
            if key in fields:
                raise ValueError("Duplicate Debian index field")
            fields[key] = value
        if (fields.get("Package"), fields.get("Architecture"), fields.get("Version")) != ("chatgpt", "amd64", version):
            continue
        if fields.get("Filename") != f"pool/main/c/chatgpt/chatgpt_{version}_amd64.deb":
            raise ValueError("Unexpected OpenAI archive path")
        checksum = fields.get("SHA256", "")
        if not re.fullmatch(r"[a-f0-9]{64}", checksum):
            raise ValueError("Invalid OpenAI SHA256 checksum")
        checksums.add(checksum)
    if len(checksums) != 1:
        raise ValueError("Expected one matching OpenAI release checksum")
    return checksums.pop()


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
    if package == "chatgpt-desktop":
        request = urllib.request.Request(config[package]["url"], headers={"User-Agent": "sparkfabrik-arch-packages/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            checksum = openai_deb_checksum(response.read().decode(), version)
        recipe, count = re.subn(r"(?m)^sha256sums_x86_64=\('[a-f0-9]{64}'\)$",
                                f"sha256sums_x86_64=('{checksum}')", recipe)
        if count != 1:
            raise ValueError("Expected one pinned OpenAI checksum assignment")
    (destination / "PKGBUILD").write_text(recipe)
    subprocess.run(["id", "builder"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["chown", "-R", "builder:builder", str(destination)], check=True)
    if package != "chatgpt-desktop":
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
