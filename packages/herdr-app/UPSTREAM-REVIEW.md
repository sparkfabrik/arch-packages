# herdr-app upstream review

Upstream ships the Herdr desktop app through an install script. This recipe reproduces only its reviewed effects; the script itself is never run. Follow the update procedure in `.sf/ai/skills/herdr-update/SKILL.md` and the reviewed install scripts section of `CONTRIBUTING.md`.

## Last review

- Date: 2026-11-11, herdr-app 0.1.15 (`core_min` 0.1.11).
- Script: `https://releases.herdr.dev/app/install.sh`, SHA256 `b636d66cf54eb42e16e47fb2be419a9ff2ded0dc1ecc3db46fb2cc193dda92c2`, stored as `upstream-install.reviewed.sh`. Identical to `distribution/install.sh` at tag `v0.1.15` in the public `herdrdev/herdr-app` repository.
- Archive: `herdr-app-linux-x86_64.tar.gz` with `herdr-app/herdr-app` (dynamically linked PIE x86-64 ELF, mode 0755), `herdr-app.svg`, `LICENSE` (Apache-2.0), `THIRD-PARTY-NOTICES`. No setuid bits, no other executables.
- Source read at `v0.1.15`: `src/update.rs`, `src/core_bin.rs`, `src/setup.rs`, `src/telemetry.rs`.

## What the script does

- **Fetches** `https://releases.herdr.dev/app/latest.json`, then the archive URL the manifest lists for the platform. `HERDR_RELEASES_URL` points both at another server.
- **Verifies** the archive SHA256 against the manifest. The manifest is unsigned and served by the same host, so this proves integrity, not authenticity. Linux builds have no signature; only macOS bundles are checked with `codesign`.
- **Counts downloads** by appending `?src=install` or `?src=reinstall` to archive URLs on the release server.
- **Writes** `~/.local/share/herdr-app` (replacing any previous copy), a `~/.local/bin/herdr-app` symlink, `~/.local/share/icons/hicolor/scalable/apps/herdr-app.svg` and `~/.local/share/applications/herdr-app.desktop`. No root, no `sudo`, no PATH or shell-rc edits; it only prints a PATH hint.
- **Refreshes** the user desktop database and icon cache, and sends a KDE `KIconLoader` D-Bus signal.
- **Installs herdr-core** when none is found, by piping `https://releases.herdr.dev/core/install.sh` into `sh`.
- **Installs no** systemd unit files or autostart entries.

## Runtime behavior of the binary

- **Self-update**: the app updates itself only when `herdr-app.svg` sits in the same folder as its binary. It then checks `app/latest.json` hourly, stages the new build beside the install folder and swaps it on restart.
- **herdr-core**: not bundled. The app looks for it on PATH, in the login shell's PATH and in the usual install folders. When none is found, its setup screen offers to pipe the core install script into `sh`.
- **Core updates**: the app checks `core/latest.json` hourly and runs `hc update`, which herdr-core refuses for a binary the user cannot write, such as a pacman-owned `/usr/bin/herdr-core`.
- **Telemetry**: on by default. One anonymous report per day goes to `https://telemetry.herdr.dev/v1/report` (counts, buckets and an install id; no terminal content, nothing from the core). `"telemetry": false` in settings, `DO_NOT_TRACK=1` or `HERDR_TELEMETRY=0` turns it off.
- **Other machines**: adding a machine from the app installs herdr-core on that host over SSH. This is an explicit user action.
- Config and state live in `~/.config/herdr-app`.

## Standing decisions

- Install the binary alone as `/usr/bin/herdr-app`, the icon in `/usr/share/icons/hicolor/scalable/apps`, our own copy of the upstream desktop entry with `Exec=herdr-app`, and the license and notices. Keeping the icon away from the binary disables the app's self-update without patching it.
- Depend on `herdr-core>=<core_min>` instead of letting the app install the core, so no install script is ever piped into a shell.
- Pin the archive by SHA256 in the PKGBUILD. The updater takes the checksum from the versioned manifest `app/<version>/manifest.json`; CI downloads and verifies the archive.
- Do not reproduce the download counter, the `~/.local` install, the cache refreshes (pacman hooks handle them) or the D-Bus signal.
- Keep upstream's telemetry default and document how to opt out.
- No launcher wrapper: the app chooses Wayland or X11 itself. No `.install` scriptlet.
- `distribution` is `local`: a vendor binary we do not build, downloaded directly from upstream by each user.
- Do not add the package to `.github/auto-merge-packages`; every bump gets a human review of the script diff.

## Recheck on every update

- New hosts, environment overrides, or download parameters in the script.
- Any signature or key upstream starts publishing; the recipe should verify it.
- New files, executables, or setuid bits in the archive.
- That self-update still depends on the icon beside the binary (`find_root` in `src/update.rs`), and that the app still leaves a pacman-owned core alone.
- Telemetry endpoint, fields and opt-out.
- The manifest's `core_min` against the `herdr-core` dependency and the packaged herdr-core version.
