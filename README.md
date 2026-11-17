# SparkFabrik Arch packages

SparkFabrik-maintained packages for Arch Linux: our own tools and binaries through a signed pacman repository, and selected vendor applications through reviewed PKGBUILD recipes in paru. Keep control of the packaging you depend on without relying on community AUR recipes.

[Get started](#install-on-arch-linux) · [Available packages](#available-packages) · [Contribute](CONTRIBUTING.md) · [License](#license)

## Why use this repository?

- **Reviewed recipes.** Packaging instructions, source URLs, and pinned checksums live in Git and require owner review when their behavior changes.
- **Two package channels.** Install our published binaries through pacman. Use paru for recipes that download directly from the vendor without us hosting their application binaries.
- **Native package tracking.** Locally built applications are installed with pacman, so their files, dependencies, and removal stay under package-manager control.
- **Automated maintenance.** Eligible version bumps merge after CI builds and tests the recipe. Paru discovers recipe updates; pacman discovers published binary updates.

Maintained by SparkFabrik. This is an independent repository, not an official Arch Linux or upstream vendor repository.

## Available packages

| Package       | Application                                           | Source                         | Architecture | Distribution                          |
| ------------- | ----------------------------------------------------- | ------------------------------ | ------------ | ------------------------------------- |
| `voice-strip` | Live microphone processing and virtual microphone     | Official GitHub release        | `x86_64`     | Signed pacman repository              |
| `herdr-core`  | Herdr terminals for coding agents (`hc` CLI and core) | Official Herdr release archive | `x86_64`     | Paru recipe, direct upstream download |
| `herdr-app`   | Herdr desktop app for terminals and coding agents     | Official Herdr release archive | `x86_64`     | Paru recipe, direct upstream download |

`herdr-core` installs `/usr/bin/herdr-core` and `/usr/bin/hc` without running Herdr's install script. Update it with paru; `hc update` declines to replace a pacman-owned binary. If you used Herdr's installer before, remove `~/.local/bin/herdr-core` and its `~/.local/bin/hc` link, which would shadow the package on PATH, then run `hc server restart` when convenient: running terminals keep running.

`herdr-app` depends on the `herdr-core` recipe and leaves app and core updates to paru. **Its launcher turns Herdr's usage telemetry off** unless you set `HERDR_TELEMETRY` yourself; start it with `HERDR_TELEMETRY=1` to let the app's own setting decide. If you used Herdr's app installer before, remove `~/.local/share/herdr-app`, `~/.local/bin/herdr-app` and `~/.local/share/applications/herdr-app.desktop`: that desktop entry has the same name and would keep launching the old, self-updating copy.

`voice-strip` is published as a signed binary package; see [Signed binary repository](#signed-binary-repository). ARM builds and publication to the AUR are outside the current scope.

> **NO WARRANTY OF ANY KIND. USE AT YOUR OWN RISK.** SparkFabrik and the contributors provide this repository, its packaging, and distributed artifacts **“AS IS” and “AS AVAILABLE,” without any express or implied warranty**, including merchantability, fitness for a particular purpose, or noninfringement. We do not guarantee security, compatibility, availability, continued maintenance, or suitability for production. To the extent permitted by applicable law, SparkFabrik and the contributors accept no liability for claims, damages, data loss, or other consequences arising from use. Third-party software remains subject to its own license terms.

## Install on Arch Linux

Use the [signed binary repository](#signed-binary-repository) to install `voice-strip` with pacman.

### ChatGPT desktop migration

OpenAI now provides an official signed Arch Linux repository. Our `chatgpt-desktop` recipe is retired and no longer receives updates. Follow [OpenAI's Arch Linux installation instructions](https://learn.chatgpt.com/docs/linux/linux-app#install-on-arch-linux) to install `chatgpt-bin` and receive updates through pacman.

An existing `chatgpt-desktop` installation remains installed until you migrate. For manual migration, review the package replacement prompt. Our custom `codex-desktop` alias, automatic Wayland selection, and `~/.config/codex-flags.conf` handling were part of the retired recipe; do not assume the official launcher supports them.

With the updated [sf-toolbox](https://github.com/sparkfabrik/archlinux-ansible-provisioner), existing `chatgpt-desktop`, `chatgpt`, and `openai-codex-desktop` installations migrate automatically to `chatgpt-bin` on the next run. Fresh desktop installations remain opt-in with `CHATGPT_DESKTOP=1`. System configuration belongs in that provisioner.

### Recipe-only packages

No recipe-only package is currently onboarded. For future recipes, paru 2 or newer can use [paru.conf](paru.conf). Add its section to your active user paru configuration:

```ini
[sparkfabrik]
Url = https://github.com/sparkfabrik/arch-packages.git
Path = packages
```

If you use `~/.config/paru/paru.conf`, it takes precedence over the system configuration. Include `/etc/paru.conf` there if needed. Keep paru's recipe review enabled.

Refresh recipes with `paru -Sy --pkgbuilds`. Select a recipe explicitly with `paru -S --pkgbuilds sparkfabrik/<pkgname>`. Paru downloads the declared source, verifies its checksum, and builds with `makepkg`; pacman tracks the installed package. Manual builds use `makepkg -si` from the package directory.

Update binary repositories and configured recipes with `paru -Syu --mode repo,pkgbuilds`. Add `aur` to that mode list if you also want community AUR updates. Pacman alone cannot update recipe-only packages. See [paru.conf(5)](https://github.com/Morganamilo/paru/blob/master/man/paru.conf.5) for custom repository support.

## Signed binary repository

It publishes `voice-strip`. Paru recipe installation does not require a pacman repository stanza or packaging-key import.

The signed pacman repository hosts our own tools and binaries, and any other packages explicitly approved for distribution. This GitHub repository and its Release assets are public; confidential internal software needs private storage and authenticated access instead. Configure it as follows.

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

Packages published through this channel use normal pacman installation and updates. Use a full system upgrade when installing, rather than a partial `pacman -Sy` update:

```bash
sudo pacman -Syu voice-strip
```

## Build and test

Run this from a checkout on Linux or macOS with Docker:

```bash
docker run --rm --platform linux/amd64 -v "${PWD}:/work" -w /work \
  archlinux:base-devel@sha256:61f7de2dd88cc4ba1fe36c24cfe1a503c3936984492d6405eeab013ce6ac68c5 \
  bash -c 'pacman-key --init && pacman -Syu --noconfirm --needed git namcap python && bash scripts/build.sh voice-strip'
```

Local test artifacts appear in `artifacts/`; disposable build files stay in `.build/`. In CI, local-only packages are built and installed in separate disposable Arch containers on the same runner. Their binaries are never uploaded as Actions artifacts or Release assets. Only approved binary packages on `main` use temporary Actions artifacts for the publication job. PR builds never upload package binaries. The scripts under `scripts/` run inside Linux containers. `makepkg` runs as an unprivileged builder; dependency installation runs as container root.

Namcap errors always fail. Each package's `namcap.allow` records reviewed warnings and reason comments. Entries are exact unless they contain `*`, which matches any run of characters within the normalized warning line; all other characters are literal.

Patterns may absorb only vendored path versions or changing `needed in files` lists. They must retain the warning type, package name, and specific library, module, or path stem. Each pattern needs a reviewed reason comment, and pattern changes require owner review rather than automatic merging. New warning meanings still fail until reviewed.

Run publication, tampering, retry, version-policy, and package-selection tests inside Arch:

```bash
python -m unittest discover -s tests -v
shellcheck scripts/*.sh
```

Publication tests use temporary keys and simulated GitHub storage, with real GPG and `repo-add`. They do not publish remotely.

## Automated updates

The daily workflow checks each package named in `nvchecker.toml`. A newer release updates `pkgver`, resets `pkgrel` to `1`, refreshes checksums with `updpkgsums`, regenerates `.SRCINFO`, and opens one PR per version. CI downloads and verifies the source before building. Existing PRs, including rejected versions, are not duplicated.

SparkFabrik PR Automation opens the PR, so CI starts without manual approval. Packages listed in `.github/auto-merge-packages` merge automatically after required CI passes. `herdr-app`, `herdr-core` and `voice-strip` are enabled. For local-only packages, merging updates the reviewed recipe; paru discovers the new version when users refresh and upgrade. It does not publish or remotely install the application.

The merge workflow runs trusted code from `main`. It accepts only App-authored PRs that change the package's version, release counter, SHA256 checksum, and corresponding `.SRCINFO`. Dependency, source-template, scriptlet, workflow, and other changes require platform-team review. The merge is bound to the tested head commit. Outdated branches are updated and tested again.

To add another package, add a single-package x86_64 PKGBUILD, `.SRCINFO`, and a `distribution` file containing `local` or `repository`, then a matching nvchecker entry. Binary publication requires explicit `repository` classification and redistribution review; missing or invalid policy fails closed. The recipe must use plain `pkgver=` and `pkgrel=` assignments. Add its name to the auto-merge list only after reviewing its upstream trust model. Automatic merging currently accepts increasing dotted numeric versions and one `sha256sums_x86_64` entry; other version shapes remain manual.

## Signing and publication

PR builds run without production signing credentials. Only packages classified as `repository` can be uploaded or published, and only on pushes to `main`. If no such package changed, the publication job is skipped and no Release is created. Eligible pushes to `main` publish through a separate job and the main-only `repository` environment. GitHub Actions are pinned to commits; the Arch image is pinned to a digest. Review and update these pins with the build workflow, then run the complete checks.

The `repo` Release contains packages, detached signatures, database aliases, files database aliases, and immutable signed snapshots. Existing packages remain available. A signed checkpoint records the last successful source commit; subsequent runs include every pending recipe change.

Packages upload before database aliases. The release checkpoint changes last. An interrupted run can rebuild from its last signed checkpoint and retry. Retries reuse previously signed packages only when their embedded recipe-tree identity matches the intended recipe; unsigned partial uploads are replaced with the newly checked build. GitHub cannot replace database and signature assets atomically, so a client may need to retry briefly during publication. Never weaken `SigLevel` to work around that.

Changing a published recipe requires a higher `pkgver` or `pkgrel`. Signed package filenames are never overwritten with different bytes. Published-package removals and epoch changes require a separate repository migration. Old assets are not pruned automatically.

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
