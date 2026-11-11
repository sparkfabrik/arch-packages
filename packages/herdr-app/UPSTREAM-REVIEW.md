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
- **Core updates**: the app reads `installed_by` from the core's `server.status` (`src/window.rs`). When it is set, as it is for a pacman-owned `/usr/bin/herdr-core` ("system package manager"), the hourly `core/latest.json` check never marks an update as ready (`check_core` in `src/update.rs`), so the app offers no herdr-core update and `app.update_core` answers "up to date". Even if `hc update` ran, herdr-core refuses to replace a binary the user cannot write. The post-update core bump runs only after an app self-update, which this package disables.
- **Telemetry**: on by default upstream. One anonymous report per day goes to `https://telemetry.herdr.dev/v1/report` (versions, OS, bucketed usage, known agent names, command names and an install id; no terminal content, paths or free text, nothing from the core). Collection runs only while the `telemetry` setting in `settings.json` (default true) is on and no environment opt-out is set. The environment is read once at startup (`env_off` in `src/telemetry.rs`): `DO_NOT_TRACK` set to `1`, `true` or `yes`, `HERDR_TELEMETRY` set to `0`, `false`, `off` or `no`, or a CI variable turns it off for that process, whatever the setting says, and Settings > Privacy shows why. An empty variable counts as unset. Turning the setting off also deletes the install id and unsent reports.
- **Other machines**: adding a machine from the app installs herdr-core on that host over SSH. This is an explicit user action.
- Config and state live in `~/.config/herdr-app`.

## Standing decisions

- Install the binary alone as `/usr/lib/herdr-app/herdr-app`, the icon in `/usr/share/icons/hicolor/scalable/apps`, our own copy of the upstream desktop entry with `Exec=herdr-app`, and the license and notices. Keeping the icon away from the binary disables the app's self-update without patching it.
- **Telemetry is off by default in this package.** `/usr/bin/herdr-app` is a small launcher, used by the desktop entry and the command line alike, that sets `HERDR_TELEMETRY=0` when the variable is unset or empty and then runs the binary. A user who wants telemetry sets `HERDR_TELEMETRY=1` (the `telemetry` setting then decides); a value the user sets is never changed. With the launcher's default, the in-app setting cannot turn telemetry on, because the environment opt-out wins for the whole run. The variable is inherited by herdr-core and the terminals it starts; herdr-core sends no telemetry.
- Depend on `herdr-core>=<core_min>` instead of letting the app install the core, so no install script is ever piped into a shell. Pacman alone updates herdr-core: the app offers no core update because the packaged core reports `installed_by`.
- Pin the archive by SHA256 in the PKGBUILD. The updater takes the checksum from the versioned manifest `app/<version>/manifest.json`; CI downloads and verifies the archive.
- Do not reproduce the download counter, the `~/.local` install, the cache refreshes (pacman hooks handle them) or the D-Bus signal.
- The launcher adds no display flags: the app chooses Wayland or X11 itself. No `.install` scriptlet.
- `distribution` is `local`: a vendor binary we do not build, downloaded directly from upstream by each user.
- Do not add the package to `.github/auto-merge-packages`; every bump gets a human review of the script diff.

## Recheck on every update

- New hosts, environment overrides, or download parameters in the script.
- Any signature or key upstream starts publishing; the recipe should verify it.
- New files, executables, or setuid bits in the archive.
- That self-update still depends on the icon beside the binary (`find_root` in `src/update.rs`).
- That the app still offers no core update when the core reports `installed_by` (`check_core` in `src/update.rs`, the `server.status` read in `src/window.rs`), and that the packaged herdr-core still reports it.
- Telemetry endpoint and fields, and that `HERDR_TELEMETRY=0` still disables collection for the whole run, whatever the setting says (`read_env_off` and `set_setting` in `src/telemetry.rs`, and `docs/security.md`).
- The manifest's `core_min` against the `herdr-core` dependency and the packaged herdr-core version.
