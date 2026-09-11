#!/usr/bin/env python3
"""Select recipes and publish signed pacman snapshots without executing recipes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

REPO = os.environ.get("GH_REPO", "sparkfabrik/arch-packages")
NAME = re.compile(r"[a-z0-9][a-z0-9+._-]*")


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def release():
    releases = json.loads(run("gh", "release", "list", "--repo", REPO, "--limit", "100", "--json", "tagName"))
    if not any(item["tagName"] == "repo" for item in releases):
        if len(releases) == 100:
            raise ValueError("Cannot establish whether the repo release exists")
        return None
    return json.loads(run("gh", "release", "view", "repo", "--repo", REPO, "--json", "body,assets,isDraft"))


def download(name, directory):
    if Path(name).name != name or not re.fullmatch(r"[a-zA-Z0-9+._-]+", name):
        raise ValueError(f"Unsafe release asset: {name}")
    target = directory / name
    run("gh", "release", "download", "repo", "--repo", REPO, "--pattern", name, "--output", str(target))
    return target


def verify(path):
    status = run("gpg", "--batch", "--status-fd", "1", "--verify", str(path) + ".sig", str(path))
    fingerprint = Path("keys/fingerprint").read_text().strip()
    valid = [line.split() for line in status.splitlines() if line.startswith("[GNUPG:] VALIDSIG ")]
    if not any(fields[2] == fingerprint or fields[-1] == fingerprint for fields in valid):
        raise ValueError("Signature does not belong to the pinned packaging key")


def checkpoint(info, directory):
    if info is None:
        return {"commit": None, "packages": {}}
    match = re.search(r"<!-- published: (state-([0-9a-f]{40})-[0-9]+\.json) -->", info["body"])
    if not match:
        if info["isDraft"]:
            return {"commit": None, "packages": {}}
        raise ValueError("Public repo release has no signed publication checkpoint")
    name = match[1]
    path = download(name, directory)
    download(name + ".sig", directory)
    verify(path)
    state = json.loads(path.read_text())
    if state["commit"] != match[2]:
        raise ValueError("Checkpoint commit mismatch")
    return state


def recipes():
    names = sorted(path.parent.name for path in Path("packages").glob("*/PKGBUILD"))
    if any(not NAME.fullmatch(name) for name in names):
        raise ValueError("Invalid package directory name")
    return names


def select(base):
    names = recipes()
    if not base or set(base) == {"0"}:
        return names
    paths = run("git", "diff", "--name-only", base, "HEAD").splitlines()
    changed = {path.split("/")[1] for path in paths if path.startswith("packages/")}
    removed = changed - set(names)
    if removed:
        raise ValueError(f"Package removal needs a separate repository migration: {sorted(removed)}")
    if any(path.startswith(("scripts/", "tests/", "keys/")) or path == ".github/workflows/build.yml" for path in paths):
        return names
    return sorted(changed)


def metadata(name):
    values = {}
    for line in Path(f"packages/{name}/.SRCINFO").read_text().splitlines():
        key, separator, value = line.strip().partition(" = ")
        if separator:
            values.setdefault(key, []).append(value)
    if values.get("pkgname") != [name] or values.get("arch") != ["x86_64"]:
        raise ValueError("v1 supports one x86_64 package per recipe")
    version = values["pkgver"][0] + "-" + values["pkgrel"][0]
    if not re.fullmatch(r"[a-zA-Z0-9.+_]+-[0-9.]+", version):
        raise ValueError("Invalid package version")
    if values.get("epoch", ["0"]) != ["0"]:
        raise ValueError("Epoch changes need an explicit repository migration")
    return version


def sign(path):
    run("gpg", "--batch", "--yes", "--local-user", Path("keys/fingerprint").read_text().strip(),
        "--detach-sign", "--no-armor", str(path))


def upload(path, assets, scratch):
    if path.name in assets:
        existing = download(path.name, scratch)
        if digest(existing) != digest(path):
            raise ValueError(f"Refusing to replace immutable asset {path.name}; bump pkgrel")
        return
    run("gh", "release", "upload", "repo", str(path), "--repo", REPO)


def publish(directory):
    info = release()
    state = checkpoint(info, directory)
    head = run("git", "rev-parse", "HEAD")
    if state["commit"]:
        run("git", "merge-base", "--is-ancestor", state["commit"], head)
    names = recipes()
    if set(state["packages"]) - set(names):
        raise ValueError("Removing published packages requires a separate migration")
    assets = {item["name"] for item in info["assets"]} if info else set()
    package_paths = []
    updated = {}
    for name in names:
        version = metadata(name)
        recipe = run("git", "rev-parse", f"HEAD:packages/{name}")
        previous = state["packages"].get(name)
        if previous and previous["recipe"] == recipe:
            path = download(previous["filename"], directory)
            download(previous["filename"] + ".sig", directory)
            verify(path)
            if digest(path) != previous["sha256"]:
                raise ValueError(f"Published checksum mismatch: {name}")
            updated[name] = previous
        else:
            if previous and previous["version"] == version:
                raise ValueError(f"Bump pkgver or pkgrel when changing {name}")
            if previous and int(run("vercmp", version, previous["version"])) <= 0:
                raise ValueError(f"Refusing version downgrade: {name}")
            path = directory / f"{name}-{version}-x86_64.pkg.tar.zst"
            source = Path("artifacts") / path.name
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"Missing regular build artifact: {source}")
            shutil.copyfile(source, path)
            pkginfo = run("bsdtar", "-xOf", str(path), ".PKGINFO")
            fields = dict(line.split(" = ", 1) for line in pkginfo.splitlines() if " = " in line)
            if (fields.get("pkgname"), fields.get("pkgver"), fields.get("arch")) != (name, version, "x86_64"):
                raise ValueError(f"Unexpected package identity: {path.name}")
            if path.name in assets:
                # Retry an interrupted publish using the already uploaded signature.
                existing = download(path.name, directory / "existing")
                if digest(existing) != digest(path):
                    raise ValueError(f"Different bytes already published for {path.name}; bump pkgrel")
            if path.name + ".sig" in assets:
                download(path.name + ".sig", directory)
                verify(path)
            else:
                sign(path)
            updated[name] = {"version": version, "recipe": recipe, "filename": path.name, "sha256": digest(path)}
        package_paths.append(path)

    db = directory / "sparkfabrik.db.tar.gz"
    if state["commit"]:
        old = state["snapshot"]
        snapshot = download(old, directory)
        download(old + ".sig", directory)
        verify(snapshot)
        shutil.copyfile(snapshot, db)
        shutil.copyfile(str(snapshot) + ".sig", str(db) + ".sig")
    run("repo-add", "--sign", "--verify", "--key", Path("keys/fingerprint").read_text().strip(),
        str(db), *(str(path) for path in package_paths))
    files = directory / "sparkfabrik.files.tar.gz"
    if not Path(str(files) + ".sig").exists():
        sign(files)
    generation = f"{head}-{time.time_ns()}"
    state_path = directory / f"state-{generation}.json"
    snapshot = directory / f"snapshot-{generation}.db.tar.gz"
    state_path.write_text(json.dumps({"commit": head, "packages": updated, "snapshot": snapshot.name}, sort_keys=True) + "\n")
    sign(state_path)
    shutil.copyfile(db, snapshot)
    shutil.copyfile(str(db) + ".sig", str(snapshot) + ".sig")

    if info is None:
        run("gh", "release", "create", "repo", "--repo", REPO, "--target", head,
            "--title", "SparkFabrik pacman repository", "--notes", "Initial repository publication in progress.", "--draft")
    scratch = directory / "compare"
    scratch.mkdir()
    for path in [*package_paths, snapshot, state_path]:
        upload(path, assets, scratch)
        upload(Path(str(path) + ".sig"), assets, scratch)
    for archive, alias in [(db, "sparkfabrik.db"), (files, "sparkfabrik.files")]:
        # GitHub assets are files, not repository symlinks.
        alias_path = directory / "aliases" / alias
        alias_path.parent.mkdir(exist_ok=True)
        shutil.copyfile(archive, alias_path)
        shutil.copyfile(str(archive) + ".sig", str(alias_path) + ".sig")
        run("gh", "release", "upload", "repo", str(archive), str(archive) + ".sig",
            str(alias_path), str(alias_path) + ".sig", "--repo", REPO, "--clobber")
    notes = directory / "release-notes.txt"
    notes.write_text("Signed x86_64 packages for SparkFabrik workstations.\n\n"
                     f"<!-- published: {state_path.name} -->\n")
    run("gh", "release", "edit", "repo", "--repo", REPO, "--notes-file", str(notes), "--draft=false")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["select", "publish"])
    parser.add_argument("--base")
    parser.add_argument("--published", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        (directory / "existing").mkdir()
        if args.command == "publish" or args.published:
            run("gpg", "--batch", "--import", "keys/sparkfabrik.asc")
            expected = Path("keys/fingerprint").read_text().strip()
            if not re.fullmatch(r"[A-F0-9]{40}", expected):
                raise ValueError("Invalid pinned signing fingerprint")
        if args.command == "publish":
            publish(directory)
        else:
            base = checkpoint(release(), directory)["commit"] if args.published else args.base
            print(json.dumps(select(base)))


if __name__ == "__main__":
    main()
