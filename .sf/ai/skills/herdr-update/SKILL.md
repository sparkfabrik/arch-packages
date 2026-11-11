---
name: herdr-update
description: Update the herdr-core or herdr-app package in this repository. Use when a version PR for herdr-core or herdr-app needs review, when the update job reports that a Herdr install script changed, or when asked to bump, re-review or repair either recipe. Covers the security review of the upstream install script, the diff against the reviewed copy, applying the result to the PKGBUILD, and the version coupling between the app and the core.
---

# Update a Herdr package

Herdr ships Linux builds through install scripts on `https://releases.herdr.dev`. Our recipes reproduce only the reviewed effects of those scripts. The maintainer does not trust the scripts: **never execute an upstream install script**, not even in a container, and never pipe one into a shell. Download scripts and archives only into a scratch directory, and read them.

## Inputs

- `CONTRIBUTING.md`: recipe rules, the Docker build, and the reviewed install script mechanism.
- `packages/<package>/UPSTREAM-REVIEW.md`: what that package's script does, the last reviewed script hash, standing decisions, and what to recheck. It is the package-specific part of this procedure; read it before step 1.
- `packages/<package>/upstream-install.reviewed.sh`: the reviewed copy of the script.
- `upstream-scripts.toml` and `nvchecker.toml`: where the script and the version come from.

## Procedure

1. **Diff the script.** Run `python scripts/upstream_scripts.py check <package>` from the repository root. It downloads the current script and prints a unified diff against the reviewed copy; exit status 1 means it changed. With no diff, go to step 4.
2. **Review every changed line** against the security checklist below, together with the unchanged code it depends on. When a change relies on behavior inside the binary (for example its self-update), read the matching source in the public upstream repository.
3. **Map the result onto the recipe.** Reproduce new legitimate effects in `package()`: files, links, licenses, desktop entries, icons. Do not reproduce downloads at install time, writes to the user's home, shell-rc or PATH edits, telemetry markers, or self-update. Record anything deliberately not reproduced as a standing decision in `UPSTREAM-REVIEW.md`.
4. **Check the artifact.** Download the archive that `https://releases.herdr.dev/<product>/<version>/manifest.json` lists for `linux-x86_64`. Compare its SHA256 with the manifest and with `sha256sums_x86_64` in the PKGBUILD, and list its contents. New files, new executables, setuid bits, or license changes need the same review as a script change. The manifest checksum proves integrity only; upstream publishes no signatures for Linux builds. If upstream starts signing, verify the signature in the recipe.
5. **Check version coupling.** The app manifest's `core_min` is the oldest herdr-core the app accepts. The herdr-app recipe must depend on `herdr-core>=<core_min>`, and the packaged herdr-core `pkgver` must satisfy it. If it does not, update herdr-core first, then raise the dependency in the same or a following PR.
6. **Record the review.** Update `UPSTREAM-REVIEW.md`: date, version, script SHA256, findings, decisions. Then run `python scripts/upstream_scripts.py accept <package> --sha256 <sha256>` with the SHA256 that `check` printed for the script you read. It refuses to write anything if upstream now serves different bytes; in that case diff and review again. If the recipe changed without a new upstream version, increase `pkgrel`.
7. **Validate** as `CONTRIBUTING.md` describes: the Docker build of `scripts/build.sh <package>`, the unit tests, shellcheck and actionlint. Never run `scripts/test-install.sh` or install the package on a workstation.
8. **Report in the PR description**: what changed upstream, its security impact, and what the recipe does about it.

## Security checklist

Apply it to the script and to everything the script downloads or runs.

- **URLs fetched**: every host and path, including those built from variables and environment overrides. A new host is a finding.
- **Verification**: checksums, signatures, keys, and where each one comes from. A checksum served next to the archive protects against corruption, not tampering.
- **Writes**: every path created, replaced, or removed, and anything outside the user's home.
- **Privileges**: `sudo`, root checks, setuid, capabilities, polkit, `loginctl`.
- **PATH and shell**: edits to shell rc files, profiles, the environment, or PATH.
- **Services and autostart**: systemd units, `systemd-run`, desktop autostart, linger.
- **Telemetry must stay off by default**: query parameters, counters, analytics endpoints, automatic update checks, and settings that default to on, in the script and in the program's source for the released tag. Anything found must be disabled by default for every way the program starts, while an explicit user setting still works; record how in `UPSTREAM-REVIEW.md`.
- **Self-update**: whether the program replaces itself or another Herdr program, and what it does when pacman owns the files.
- **Executed code**: every program the script runs, including the downloaded one and nested install scripts.
