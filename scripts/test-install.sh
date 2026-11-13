#!/usr/bin/env bash
set -euo pipefail

# Only run in a fresh disposable Arch container. This changes its pacman keyring.
package="${1:?package name required}"
[[ "${package}" =~ ^[a-z0-9][a-z0-9+._-]*$ ]]
export GNUPGHOME
GNUPGHOME=$(mktemp -d)
trap 'gpgconf --kill gpg-agent' EXIT
gpg --batch --pinentry-mode loopback --passphrase '' \
  --quick-generate-key 'Disposable package test' ed25519 sign 1d
fingerprint=$(gpg --with-colons --list-keys | awk -F: '$1 == "fpr" { print $10; exit }')
for artifact in artifacts/*.pkg.tar.zst; do
  gpg --batch --detach-sign --no-armor "${artifact}"
done
repo-add -s -k "${fingerprint}" artifacts/sparkfabrik-test.db.tar.gz artifacts/*.pkg.tar.zst
gpg --export "${fingerprint}" > "${GNUPGHOME}/public.gpg"
pacman-key --add "${GNUPGHOME}/public.gpg"
pacman-key --lsign-key "${fingerprint}"
cat >> /etc/pacman.conf <<EOF

[sparkfabrik-test]
SigLevel = Required TrustedOnly
Server = file://${PWD}/artifacts
EOF
pacman -Syu --noconfirm "${package}"
LC_ALL=C pacman -Qi "${package}" | tee /tmp/package-info.txt
grep -Eq '^Validated By[[:space:]]*:.*Signature' /tmp/package-info.txt
