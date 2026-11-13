# herdr-core upstream review

Upstream ships herdr-core (`hc`) through an install script. This recipe reproduces only its reviewed effects; the script itself is never run. Follow the update procedure in `.sf/ai/skills/herdr-update/SKILL.md` and the reviewed install scripts section of `CONTRIBUTING.md`.

## Last review

- Date: 2026-11-13, herdr-core 0.1.20 (script as served when 0.1.21 was latest).
- Script: `https://releases.herdr.dev/core/install.sh`, SHA256 `9d29a920d796d11b00fde9ab0958b616179d88acc25edf0fde8b574bde0227d2`, stored as `upstream-install.reviewed.sh`.
- Change since the 2026-11-11 review: when the downloaded binary cannot run from the temp directory (for example a `noexec` `/tmp`), the script copies it to `<install dir>/herdr-core.staged`, runs `--version` there, installs or updates from that copy, and removes it on exit. No new hosts, privileges, or environment overrides; the recipe does not reproduce the `~/.local/bin` install, so it needs no change.
- Archive: `herdr-core-linux-x86_64.tar.gz` with `herdr-core` (static-pie x86-64 ELF, mode 0755), `LICENSE` (Apache-2.0), `THIRD-PARTY-NOTICES`.

## What the script does

- **Fetches** `https://releases.herdr.dev/core/latest.json`, or `core/<HC_VERSION>/manifest.json`, then the archive URL the manifest lists for the platform. `HERDR_RELEASES_URL` points both at another server.
- **Verifies** the archive SHA256 against the manifest. The manifest is unsigned and served by the same host, so this proves integrity, not authenticity; upstream `docs/security.md` says the same. Linux builds have no other signature; only macOS bundles are checked with `codesign`.
- **Counts downloads** by appending `?src=install` or `?src=update` to archive URLs on the release server.
- **Runs** the downloaded `herdr-core --version` before installing it. If that fails, it stages the binary as `herdr-core.staged` in the install folder, re-runs the check there, and deletes the staged copy on exit.
- **Writes** `~/.local/bin/herdr-core` (or `HC_INSTALL_DIR`), and an `hc` symlink only when no `hc` is on PATH or in that folder. No root, no `sudo`, no PATH or shell-rc edits; it only prints a PATH hint.
- **Updates** an existing install by running `herdr-core update --from <download>`, which swaps the binary and restarts the running core.
- **Installs no** systemd unit files or autostart entries, and sends no telemetry beyond the download counter.

## Runtime behavior of the binary

- `hc update` refuses to replace a binary in a folder the user cannot write and tells the user to update it with the package manager (upstream `client::installed_by()`). Running `hc update` as root would bypass pacman.
- The core starts on demand as transient systemd user units (`systemd-run --user`); no unit files are installed. When linger is off, the first service start runs `loginctl --no-ask-password enable-linger <user>` once; polkit decides whether that succeeds, otherwise hc prints a hint. Linger keeps the user manager running after logout.
- **No telemetry and no phone-home.** Checked in the `v0.1.20` source (`de97ea5`): the binary reaches the network only through `curl` in `releases.rs`, called by an explicit `hc update` and by `hc machine add|update`; a source comment states hc never checks for updates on its own. It sends no download counter on Linux. The server reports `installed_by` to clients such as the app, so they do not offer updates for a pacman install.
- `hc machine add` and `hc machine update` copy herdr-core to remote machines over SSH, or run an embedded installer there. These are explicit user actions.
- State lives in `~/.local/state/herdr-core`, config in `~/.config/herdr-core`, sockets in `$XDG_RUNTIME_DIR/herdr-core`.

## Standing decisions

- Install `/usr/bin/herdr-core` and the `/usr/bin/hc` symlink, plus the license and notices. Pacman reports a conflict if another package owns `/usr/bin/hc`.
- Pin the archive by SHA256 in the PKGBUILD. The updater takes the checksum from the versioned manifest `core/<version>/manifest.json`; CI downloads and verifies the archive.
- Do not reproduce the download counter, the `~/.local/bin` install, or the update swap.
- Ship no systemd units and no `.install` scriptlet; the core manages its own transient user units.
- `distribution` is `local`: a vendor binary we do not build, downloaded directly from upstream by each user.
- Telemetry stays off by default. herdr-core has none today, so the recipe changes nothing. If upstream adds telemetry or automatic update checks, disable them by default for every launch path (`hc`, the core server, and cores started by herdr-app), keep an explicit user setting working, and record how here.
- The package is listed in `.github/auto-merge-packages`. A version-only bump (new `pkgver` and manifest checksum) merges automatically when its PR build passes; that build fails while the install script differs from `upstream-install.reviewed.sh`. A changed script, a failed build, and any other recipe change need a human review with this file.

## Recheck at every human review

Automatic version merges do not run these checks. A human review covers every release since the version in Last review.


- New hosts, environment overrides, or download parameters in the script.
- Any signature or key upstream starts publishing; the recipe should verify it.
- New files, executables, or setuid bits in the archive.
- Whether `hc update` still refuses a binary in `/usr/bin`, and whether the core gains services or autostart.
- Telemetry and phone-home: search the release source for network clients (`curl`, HTTP libraries, sockets to non-local hosts), analytics or telemetry settings, and automatic update checks. Any new one must be off by default.
- The herdr-app `core_min` against the packaged version. The updater raises the herdr-app `herdr-core>=` floor when `core_min` rises, and that PR needs a human review.
