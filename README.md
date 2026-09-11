# SparkFabrik Arch packages

SparkFabrik-maintained packages for Arch Linux. Install prebuilt applications with pacman and keep them updated alongside the rest of your system. Open to anyone running a supported Arch Linux system.

[Get started](#install-on-arch-linux) · [Available packages](#available-packages) · [Contribute](CONTRIBUTING.md) · [License](#license)

## Why use this repository?

- **Native package management.** Install, upgrade, and remove applications with the pacman commands you already use.
- **Ready-to-install binaries.** Builds happen in CI, so your workstation does not need to run AUR recipes.
- **Signed releases.** Pacman verifies packages and repository databases against the trusted packaging key.
- **Visible maintenance.** Recipes and workflows live in Git. Packaging changes receive owner review; eligible version updates merge after automated checks pass.

Maintained by SparkFabrik. This is an independent repository, not an official Arch Linux or upstream vendor repository.

## Available packages

| Package           | Application     | Source                   | Architecture |
| ----------------- | --------------- | ------------------------ | ------------ |
| `chatgpt-desktop` | ChatGPT desktop | OpenAI's official `.deb` | `x86_64`     |

ARM builds and publication to the AUR are outside the current scope. See [Contributing](CONTRIBUTING.md) to propose another package.

> **NO WARRANTY OF ANY KIND. USE AT YOUR OWN RISK.** SparkFabrik and the contributors provide this repository, its packaging, and distributed artifacts **“AS IS” and “AS AVAILABLE,” without any express or implied warranty**, including merchantability, fitness for a particular purpose, or noninfringement. We do not guarantee security, compatibility, availability, continued maintenance, or suitability for production. To the extent permitted by applicable law, SparkFabrik and the contributors accept no liability for claims, damages, data loss, or other consequences arising from use. Third-party software remains subject to its own license terms.

## Install on Arch Linux

Download the public key and verify its primary fingerprint before trusting it:

```bash
curl -fL -o /tmp/sparkfabrik.asc \
  https://raw.githubusercontent.com/sparkfabrik/arch-packages/main/keys/sparkfabrik.asc
fingerprint=$(gpg --show-keys --with-colons /tmp/sparkfabrik.asc | awk -F: '$1 == "fpr" { print $10; exit }')
test "${fingerprint}" = CC54D2480F42AB0EE8E63DF91BE396C8C99CB4BE
```

Only after that check succeeds:

```bash
sudo pacman-key --init
sudo pacman-key --add /tmp/sparkfabrik.asc
sudo pacman-key --lsign-key CC54D2480F42AB0EE8E63DF91BE396C8C99CB4BE
```

Append this stanza after the distribution repositories in `/etc/pacman.conf`:

```ini
[sparkfabrik]
SigLevel = Required TrustedOnly
Server = https://github.com/sparkfabrik/arch-packages/releases/download/repo
```

Install and inspect the package:

```bash
sudo pacman -Syu chatgpt-desktop
pacman -Qi chatgpt-desktop
chatgpt
```

Use a full system upgrade with installation, rather than `pacman -Sy` followed by individual package installs. Future `pacman -Syu` runs update installed SparkFabrik packages too.

The package preserves OpenAI's launcher, desktop file, and AppArmor profile. It does not execute Debian maintainer scripts or disable Chromium's sandbox. On AppArmor installations that restrict user namespaces, load the bundled profile through your existing AppArmor administration process. No root install scriptlet is included.

## Provisioner integration

In [archlinux-ansible-provisioner](https://github.com/sparkfabrik/archlinux-ansible-provisioner), set:

```yaml
sparkfabrik_arch_repo: true
```

The default is `false`. Enabling it imports the fingerprint-checked key and configures the repository before package tasks, including tagged package runs. It does not install ChatGPT. Debian is unchanged; enabled ARM hosts fail with an unsupported-architecture message. If you previously added the repository manually, remove that stanza before enabling provisioning; an unmanaged entry causes a clear failure before configuration changes.

Setting the option back to `false` skips management; it does not remove previously installed configuration or trust. To unsubscribe, remove the marked repository stanza explicitly.

## Build and test

Run this from a checkout on Linux or macOS with Docker:

```bash
docker run --rm --platform linux/amd64 -v "${PWD}:/work" -w /work \
  archlinux:base-devel@sha256:61f7de2dd88cc4ba1fe36c24cfe1a503c3936984492d6405eeab013ce6ac68c5 \
  bash -c 'pacman-key --init && pacman -Syu --noconfirm --needed git namcap python && bash scripts/build.sh chatgpt-desktop'
```

Artifacts appear in `artifacts/`; disposable build files stay in `.build/`. The scripts under `scripts/` run inside Linux containers. `makepkg` runs as an unprivileged builder; dependency installation runs as container root.

Namcap errors always fail. `packages/chatgpt-desktop/namcap.allow` lists exact upstream warnings and reasons: precompiled ELF hardening, bundled runtimes, optional integrations, and private documentation. New warnings fail until reviewed. Non-Linux macOS prebuilds are excluded to avoid namcap mistaking Mach-O files for Java classes.

Run publication, tampering, retry, version-policy, and package-selection tests inside Arch:

```bash
python -m unittest discover -s tests -v
shellcheck scripts/*.sh
```

Publication tests use temporary keys and simulated GitHub storage, with real GPG and `repo-add`. They do not publish remotely. GUI launch and login still need validation in an actual desktop session.

## Automated updates

The daily workflow checks each package named in `nvchecker.toml`. A newer release updates `pkgver`, resets `pkgrel` to `1`, runs `updpkgsums`, regenerates `.SRCINFO`, and opens one PR per version. Existing PRs, including rejected versions, are not duplicated.

SparkFabrik PR Automation opens the PR, so CI starts without manual approval. Packages listed in `.github/auto-merge-packages` merge automatically after required CI passes. `chatgpt-desktop` is enabled initially.

The merge workflow runs trusted code from `main`. It accepts only App-authored PRs that change the package's version, release counter, SHA256 checksum, and corresponding `.SRCINFO`. Dependency, source-template, scriptlet, workflow, and other changes require platform-team review. The merge is bound to the tested head commit. Outdated branches are updated and tested again.

To add another package, add a single-package x86_64 PKGBUILD and `.SRCINFO`, then a matching nvchecker entry. The recipe must use plain `pkgver=` and `pkgrel=` assignments. Add its name to the auto-merge list only after reviewing its upstream trust model. Automatic merging currently accepts increasing dotted numeric versions and one `sha256sums_x86_64` entry; other version shapes remain manual.

## Signing and publication

PR builds run without signing credentials. Pushes to `main` build and publish through a separate publication job and the main-only `repository` environment. GitHub Actions are pinned to commits; the Arch image is pinned to a digest. Review and update these pins with the build workflow, then run the complete checks.

The `repo` Release contains packages, detached signatures, database aliases, files database aliases, and immutable signed snapshots. Existing packages remain available. A signed checkpoint records the last successful source commit; subsequent runs include every pending recipe change.

Packages upload before database aliases. The release checkpoint changes last. An interrupted run can rebuild from its last signed checkpoint and retry. Retries reuse previously signed packages only when their embedded recipe-tree identity matches the intended recipe; unsigned partial uploads are replaced with the newly checked build. GitHub cannot replace database and signature assets atomically, so a client may need to retry briefly during publication. Never weaken `SigLevel` to work around that.

Changing a published recipe requires a higher `pkgver` or `pkgrel`. Signed package filenames are never overwritten with different bytes. Package removals and epoch changes require a separate repository migration. Old assets are not pruned automatically.

If a package loses its signature after reaching the live database but before its checkpoint is recorded, automatic recovery stops. Submit a reviewed `pkgrel` bump and publish the new package filename to restore repository operation.

The packaging fingerprint is `CC54D2480F42AB0EE8E63DF91BE396C8C99CB4BE`. The certification key expires in 2028; the signing subkey expires in 2027. Keep the certification key and revocation certificate offline. Before expiry, create a replacement signing subkey, update the public key and provisioner copy through review, and replace `PACKAGING_KEY`. For a compromised primary key, distribute a new fingerprint through a reviewed trust migration before resuming publication.

Required GitHub configuration:

- `repository` environment: branches restricted to `main`; `PACKAGING_KEY` contains only the exported signing subkey and primary-key stub.
- `updates` environment: branches restricted to `main`; `SF_PR_AUTOMATION_PRIVATE_KEY` contains the existing App key. Organization variable `SF_PR_AUTOMATION_CLIENT_ID` is shared with this repository.
- SparkFabrik PR Automation installation: access to this repository, with contents and pull-request write permissions. Each workflow requests a repository-scoped installation token.
- Main protection: `Package checks` from GitHub Actions, up-to-date branches, one code-owner review, stale-review dismissal, and no force pushes or deletion. Only the automation App bypasses the review requirement; status checks still apply.

Write access and signing credentials can affect root-level package installation on subscribed machines. Review PKGBUILDs and workflow changes accordingly. Vendor binaries retain their own licensing terms; recipe ownership does not grant rights to the bundled software.

## License

SparkFabrik-authored packaging recipes, automation, and documentation are licensed under the [MIT License](LICENSE). You may use, modify, and share them under its terms, including its warranty and liability disclaimer.

**The MIT license does not relicense packaged applications or other third-party material.** Those retain their upstream licenses, copyright notices, trademarks, and terms of use. Installing a package does not grant rights beyond those terms.
