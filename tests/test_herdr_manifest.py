import json
from pathlib import Path
import re
import tomllib
import unittest
from unittest.mock import patch
from test_repository import updater


class HerdrManifestTests(unittest.TestCase):
    def manifest(self, version="0.1.20", product="core", checksum="a" * 64, **changes):
        url = f"https://releases.herdr.dev/{product}/{version}/herdr-{product}-linux-x86_64.tar.gz"
        data = {"version": version, "targets": {
            "linux-aarch64": {"url": url.replace("x86_64", "aarch64"), "sha256": "b" * 64},
            "linux-x86_64": {"url": url, "sha256": checksum}}}
        data.update(changes)
        return json.dumps(data)

    def test_selects_the_linux_x86_64_checksum(self):
        self.assertEqual(updater.herdr_manifest_checksum(self.manifest(), "core", "0.1.20"), "a" * 64)
        self.assertEqual(updater.herdr_manifest_checksum(self.manifest(product="app"), "app", "0.1.20"), "a" * 64)

    def test_rejects_wrong_version_product_url_and_checksum(self):
        good = self.manifest()
        cases = [
            (self.manifest(version="0.1.19"), "core", "0.1.20"),
            (good, "app", "0.1.20"),
            (good.replace("https://releases.herdr.dev/core/0.1.20/", "https://example.com/"), "core", "0.1.20"),
            (self.manifest(checksum="SKIP"), "core", "0.1.20"),
            (self.manifest(checksum="A" * 64), "core", "0.1.20"),
            (self.manifest(targets={}), "core", "0.1.20"),
            (self.manifest(targets=[]), "core", "0.1.20"),
            ('{"version":"0.1.20","version":"0.1.20","targets":{}}', "core", "0.1.20"),
            (good.replace('"sha256": "' + "a" * 64 + '"',
                          '"sha256": "' + "a" * 64 + '", "sha256": "' + "c" * 64 + '"'), "core", "0.1.20"),
            ("[]", "core", "0.1.20"),
        ]
        for manifest, product, version in cases:
            with self.subTest(manifest=manifest, product=product), self.assertRaises(ValueError):
                updater.herdr_manifest_checksum(manifest, product, version)

    def test_reads_the_versioned_manifest_for_herdr_packages(self):
        with patch.object(updater, "fetch", return_value=self.manifest()) as fetch:
            config = {"herdr-core": {"url": "https://releases.herdr.dev/core/latest.json"}}
            self.assertEqual(updater.indexed_checksum("herdr-core", "0.1.20", config), "a" * 64)
        fetch.assert_called_once_with("https://releases.herdr.dev/core/0.1.20/manifest.json")

    def test_other_packages_use_updpkgsums(self):
        configs = [{"github": "paolomainardi/voice-strip"},
                   {"url": "https://releases.herdr.dev.example.com/core/latest.json"},
                   {"url": "https://releases.herdr.dev/core/latest.json?x=1"}]
        for entry in configs:
            with self.subTest(entry=entry), patch.object(updater, "fetch") as fetch:
                self.assertIsNone(updater.indexed_checksum("voice-strip", "0.7.6", {"voice-strip": entry}))
            fetch.assert_not_called()

    def test_nvchecker_reads_only_the_top_level_version(self):
        root = Path(__file__).resolve().parents[1]
        config = tomllib.loads((root / "nvchecker.toml").read_text())
        for name, entry in config.items():
            if str(entry.get("url", "")).startswith(updater.HERDR_RELEASES):
                with self.subTest(package=name):
                    manifest = '{\n  "version": "0.1.20",\n  "notes": "{\\"version\\": \\"9.9.9\\"}",\n  "targets": {}\n}'
                    self.assertEqual(re.findall(entry["regex"], manifest), ["0.1.20"])
                    self.assertEqual(re.findall(entry["regex"], '{"notes": "x", "version": "9.9.9"}'), [])
