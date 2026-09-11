# Contributing to SparkFabrik Arch packages

This guide is for contributors to SparkFabrik-maintained Arch Linux packages. Submit changes through pull requests; `@sparkfabrik/platform-team` owns review.

## Choose the change

- **New package:** add a recipe, metadata, and an upstream version source. Start with manual review before enabling automatic merges.
- **Upstream update:** let the scheduled updater open the PR, or prepare a manual version bump when intervention is needed.
- **Packaging fix:** keep `pkgver` unchanged and increase `pkgrel`. Explain the resulting installation or runtime change.
- **Workflow or signing change:** request platform-team review and run the repository checks.

Currently, recipes must produce one x86_64 package. Split packages, ARM builds, epoch changes, and package removals need a separate repository design or migration.

## Start a branch

Clone the repository and branch from current `main`. Use Conventional Commits for commit subjects and PR titles, for example `feat(packages): add example desktop package` or `fix(chatgpt-desktop): correct launcher dependency`. Reference a related issue when one exists. AI-assisted commits must include an `Assisted-by` trailer identifying the agent and model.

Do not push directly to `main`. Human-authored changes require one code-owner approval and a passing `Package checks` result. New commits dismiss stale approvals.

## Add or change a recipe

Keep each package in `packages/<pkgname>/`, with its `PKGBUILD`, generated `.SRCINFO`, and any auxiliary files. Use `packages/chatgpt-desktop/` as a reference, adapting dependencies and extraction to the actual upstream artifact.

Review these details before submitting:

- Download from the official upstream source over HTTPS. Pin SHA256 checksums with `updpkgsums`; do not use `SKIP` for downloaded binaries.
- Install the upstream license and declare runtime dependencies. Preserve launcher behavior and desktop integration.
- Review archive contents, executable permissions, system configuration, and any bundled services. Do not execute foreign-package maintainer scripts as part of repackaging.
- Treat `.install` scriptlets as root code: justify each operation and review upgrades and removal as well as first installation.
- Increase `pkgver` or `pkgrel` whenever a published recipe changes. Published package filenames cannot be replaced with different bytes.

`makepkg --printsrcinfo` generates `.SRCINFO`; do not maintain it by hand. Commit both recipe and metadata together.

## Prepare metadata and build

Use Docker on Linux or macOS. The explicit platform also supports Apple Silicon hosts through Docker's amd64 emulation. From the repository root, start a disposable Arch environment:

```bash
docker run --rm -it --platform linux/amd64 \
  -v "${PWD}:/work" -w /work \
  archlinux:base-devel@sha256:61f7de2dd88cc4ba1fe36c24cfe1a503c3936984492d6405eeab013ce6ac68c5 \
  bash
```

Inside that container, replace the package name as needed:

```bash
set -euo pipefail
package=chatgpt-desktop
pacman-key --init
pacman -Syu --noconfirm --needed git namcap python pacman-contrib shellcheck actionlint
useradd --create-home builder
mkdir -p ".build/contribute/${package}"
cp -a "packages/${package}/." ".build/contribute/${package}/"
chown -R builder:builder ".build/contribute/${package}"
(
  cd ".build/contribute/${package}"
  runuser -u builder -- updpkgsums
  runuser -u builder -- makepkg --printsrcinfo > .SRCINFO
)
cp ".build/contribute/${package}/PKGBUILD" "packages/${package}/PKGBUILD"
cp ".build/contribute/${package}/.SRCINFO" "packages/${package}/.SRCINFO"
bash scripts/build.sh "${package}"
python -m unittest discover -s tests -v
shellcheck scripts/*.sh
actionlint
```

Inspect checksum changes against the intended upstream download. Regenerating a checksum records the downloaded bytes; it does not establish their authenticity. Build artifacts appear under `artifacts/`.

Namcap errors fail the build. If a vendor binary produces an unavoidable warning, add its exact text and a reason to that package's `namcap.allow`. Fix actionable findings first; do not copy another package's exceptions wholesale. New warnings require review.

CI also installs the artifact from a signed test repository in fresh Arch. For desktop packages, launch the application in a real desktop session and report what you exercised. Do not run `scripts/test-install.sh` on a workstation: it changes the system package configuration and keyring.

## Configure upstream updates

Add an entry to `nvchecker.toml` whose name matches the package directory. Choose an upstream source that returns exactly one current version. Recipes used by the updater need plain `pkgver=` and `pkgrel=` assignments.

The daily **Check upstream versions** workflow checks every entry. It can also be dispatched manually on `main`. It updates the version and checksums, resets `pkgrel` to `1`, regenerates metadata, and opens a PR through SparkFabrik PR Automation. An existing PR for that version, even a closed one, prevents duplicate PRs.

Adding a package to `.github/auto-merge-packages` opts it into automatic merging and requires owner review. The current guard accepts only increasing dotted numeric versions and one architecture-specific SHA256 checksum. Only App-authored PRs changing those fields and matching metadata qualify. Source URLs, dependencies, scripts, exceptions, and workflow changes still require review. Required checks must pass on the tested commit; outdated branches are updated and checked again.

If an update fails, inspect its build or install logs and fix the cause through a reviewed PR. Never weaken signature checks or broaden warning exceptions merely to unblock an update. A manual correction needs human review even if it started as an automated bump.

## Submit and publish

Describe the package change, upstream source, and validation performed. Include desktop launch results where applicable and call out root scriptlets or system configuration changes. Keep unrelated changes in separate PRs.

After merge, CI rebuilds changed packages, signs them, and publishes the `repo` Release. Contributors do not need the packaging private key or App private key. Never commit either credential or upload unsigned packages manually. Clients receive published updates through `pacman -Syu`.

For interrupted publication and key maintenance, see [Signing and publication](README.md#signing-and-publication). Keep `SigLevel = Required TrustedOnly` in client configuration.
