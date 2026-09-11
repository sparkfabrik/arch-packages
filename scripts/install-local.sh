#!/usr/bin/env bash
set -euo pipefail

if [[ $(uname -s) != Linux || ! -f /etc/arch-release || ${EUID} == 0 ]]; then
  echo 'Run as a regular user on Arch Linux. Only dependency and package installation use sudo.' >&2
  exit 1
fi
for tool in git bsdtar makepkg namcap python sudo; do
  command -v "${tool}" >/dev/null || { echo "Missing required tool: ${tool}" >&2; exit 1; }
done
root=$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." rev-parse --show-toplevel)
package="${1:?usage: bash scripts/install-local.sh package-name}"
[[ "${package}" =~ ^[a-z0-9][a-z0-9+._-]*$ ]]
git -C "${root}" fetch --no-tags https://github.com/sparkfabrik/arch-packages.git main
git -C "${root}" merge-base --is-ancestor HEAD FETCH_HEAD || {
  echo 'The checked-out commit is not part of reviewed upstream main.' >&2; exit 1;
}
git -C "${root}" diff --quiet HEAD -- scripts "packages/${package}" || {
  echo 'Commit or discard local script and recipe changes before installing.' >&2; exit 1;
}
mode=$(git -C "${root}" show "HEAD:packages/${package}/distribution")
[[ "${mode}" == local ]] || { echo 'This package is not designated for local installation.' >&2; exit 1; }

umask 077
cache="${XDG_CACHE_HOME:-${HOME}/.cache}/sparkfabrik-arch-packages"
mkdir -p "${cache}"
work=$(mktemp -d "${cache}/${package}.XXXXXXXX")
# Use the committed recipe, including its auxiliary files and pinned checksums.
git -C "${root}" archive HEAD "packages/${package}" | bsdtar -xf - -C "${work}"
cd "${work}/packages/${package}"
makepkg --printsrcinfo > generated.SRCINFO
diff -u .SRCINFO generated.SRCINFO
version=$(awk '$1 == "pkgver" { v=$3 } $1 == "pkgrel" { r=$3 } END { print v "-" r }' .SRCINFO)
installed=$(pacman -Q "${package}" 2>/dev/null | cut -d ' ' -f 2 || true)
if [[ -n "${installed}" && $(vercmp "${installed}" "${version}") -ge 0 ]]; then
  echo "${package} ${installed} is already installed; no upgrade needed."
  exit 0
fi
export PACKAGER
PACKAGER="SparkFabrik local build (recipe $(git -C "${root}" rev-parse "HEAD:packages/${package}"))"
makepkg -sf --syncdeps --noconfirm
mapfile -t artifacts < <(makepkg --packagelist)
[[ ${#artifacts[@]} == 1 && -f "${artifacts[0]}" && ! -L "${artifacts[0]}" ]]
python "${root}/scripts/lint.py" --errors-only namcap.allow PKGBUILD "${artifacts[0]}"
sudo pacman -U --needed --noconfirm -- "${artifacts[0]}"
echo "Installed ${package} from the local build. Build files: ${work}"
