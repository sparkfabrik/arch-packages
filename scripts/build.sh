#!/usr/bin/env bash
set -euo pipefail

# Run inside the disposable Arch container as root; makepkg runs as builder.
cd "$(dirname "${BASH_SOURCE[0]}")/.."
root="${PWD}"
package="${1:?package directory name required}"
[[ "${package}" =~ ^[a-z0-9][a-z0-9+._-]*$ ]]
[[ -f "packages/${package}/PKGBUILD" ]]
id builder >/dev/null 2>&1 || useradd --create-home builder
mkdir -p ".build/${package}" artifacts
cp -a "packages/${package}/." ".build/${package}/"
chown -R builder:builder ".build/${package}"
cd ".build/${package}"
runuser -u builder -- makepkg --printsrcinfo > generated.SRCINFO
diff -u "${root}/packages/${package}/.SRCINFO" generated.SRCINFO
mapfile -t dependencies < <(awk '$1 ~ /^(depends|makedepends|checkdepends)(_x86_64)?$/ {print $3}' generated.SRCINFO)
if (( ${#dependencies[@]} )); then
  pacman -S --needed --noconfirm -- "${dependencies[@]}"
fi
SOURCE_DATE_EPOCH="$(git -c "safe.directory=${root}" -C "${root}" log -1 --format=%ct)"
export SOURCE_DATE_EPOCH
recipe=$(git -c "safe.directory=${root}" -C "${root}" rev-parse "HEAD:packages/${package}")
export PACKAGER="SparkFabrik platform team (recipe ${recipe})"
runuser -u builder -- makepkg -sf --noconfirm
runuser -u builder -- python "${root}/scripts/lint.py" "${root}/packages/${package}/namcap.allow" PKGBUILD ./*.pkg.tar.zst
for artifact in ./*.pkg.tar.zst; do
  [[ -f "${artifact}" && ! -L "${artifact}" ]]
  cp "${artifact}" "${root}/artifacts/"
done
