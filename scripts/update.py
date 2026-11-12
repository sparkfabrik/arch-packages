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

HERDR_RELEASES = "https://releases.herdr.dev"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "sparkfabrik-arch-packages/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode()


def herdr_manifest(manifest, product, version):
    """The parsed release manifest, after checking its version, URL and checksum."""
    def unique(pairs):
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate Herdr manifest field")
        return dict(pairs)
    data = json.loads(manifest, object_pairs_hook=unique)
    if not isinstance(data, dict) or data.get("version") != version:
        raise ValueError("Herdr manifest is for another version")
    targets = data.get("targets")
    entry = targets.get("linux-x86_64") if isinstance(targets, dict) else None
    if not isinstance(entry, dict):
        raise ValueError("Herdr manifest has no linux-x86_64 build")
    if entry.get("url") != f"{HERDR_RELEASES}/{product}/{version}/herdr-{product}-linux-x86_64.tar.gz":
        raise ValueError("Unexpected Herdr archive URL")
    checksum = entry.get("sha256")
    if not isinstance(checksum, str) or not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("Invalid Herdr SHA256 checksum")
    return data


def herdr_manifest_checksum(manifest, product, version):
    return herdr_manifest(manifest, product, version)["targets"]["linux-x86_64"]["sha256"]


def herdr_product(package, config):
    """The Herdr product whose <product>/latest.json the nvchecker entry reads, or None."""
    herdr = re.fullmatch(rf"{re.escape(HERDR_RELEASES)}/([a-z]+)/latest\.json", config[package].get("url", ""))
    return herdr[1] if herdr else None


def fetch_herdr_manifest(product, version):
    return herdr_manifest(fetch(f"{HERDR_RELEASES}/{product}/{version}/manifest.json"), product, version)


def numeric_version(text):
    return tuple(map(int, text.split(".")))


def raise_core_floor(recipe, manifest):
    """Raise the recipe's herdr-core>= floor to the app manifest's core_min; never lower it.

    A raised floor changes depends, so the auto-merge guard hands the PR to a human.
    """
    core_min = manifest.get("core_min")
    if not isinstance(core_min, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", core_min):
        raise ValueError("Herdr app manifest has no valid core_min")
    floors = list(re.finditer(r"(?<![\w.+-])herdr-core>=([0-9]+(?:\.[0-9]+)*)(?=['\"\s)])", recipe))
    if len(floors) != 1:
        raise ValueError("Expected one herdr-core>= dependency in the recipe")
    floor = floors[0]
    required, current = numeric_version(core_min), numeric_version(floor[1])
    width = max(len(required), len(current))
    if required + (0,) * (width - len(required)) <= current + (0,) * (width - len(current)):
        return recipe
    print(f"Raising the herdr-core floor from {floor[1]} to {core_min}", file=sys.stderr)
    return recipe[:floor.start(1)] + core_min + recipe[floor.end(1):]


def indexed_checksum(package, version, config):
    """The archive checksum published by upstream, or None to use updpkgsums."""
    if package == "chatgpt-desktop":
        return openai_deb_checksum(fetch(config[package]["url"]), version)
    # A Herdr product's versioned manifest lists each archive's SHA256.
    product = herdr_product(package, config)
    if product:
        return fetch_herdr_manifest(product, version)["targets"]["linux-x86_64"]["sha256"]
    return None


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
    product = herdr_product(package, config)
    if product:
        manifest = fetch_herdr_manifest(product, version)
        checksum = manifest["targets"]["linux-x86_64"]["sha256"]
        if product == "app":
            recipe = raise_core_floor(recipe, manifest)
    else:
        checksum = indexed_checksum(package, version, config)
    if checksum is not None:
        recipe, count = re.subn(r"(?m)^sha256sums_x86_64=\('[a-f0-9]{64}'\)$",
                                f"sha256sums_x86_64=('{checksum}')", recipe)
        if count != 1:
            raise ValueError("Expected one pinned upstream checksum assignment")
    (destination / "PKGBUILD").write_text(recipe)
    subprocess.run(["id", "builder"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["chown", "-R", "builder:builder", str(destination)], check=True)
    if checksum is None:
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
