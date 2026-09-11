import re
import tomllib
import unittest
from pathlib import Path
from test_repository import updater


class DebianIndexTests(unittest.TestCase):
    def record(self, version="26.1.1", checksum="a" * 64, package="chatgpt", arch="amd64"):
        return f"Package: {package}\nVersion: {version}\nArchitecture: {arch}\nFilename: pool/main/c/chatgpt/chatgpt_{version}_amd64.deb\nSHA256: {checksum}\n"

    def test_selects_exact_package_version_and_architecture(self):
        index = "\n".join([self.record(package="other"), self.record(version="26.0.1"), self.record(arch="arm64"), self.record()])
        self.assertEqual(updater.openai_deb_checksum(index, "26.1.1"), "a" * 64)

    def test_rejects_missing_ambiguous_and_malformed_metadata(self):
        records = [self.record(arch="arm64"), self.record(checksum="SKIP"),
                   self.record() + "\n" + self.record(checksum="b" * 64),
                   self.record().replace("pool/main", "../main"),
                   self.record() + "SHA256: " + "b" * 64 + "\n"]
        for index in records:
            with self.subTest(index=index), self.assertRaises(ValueError):
                updater.openai_deb_checksum(index, "26.1.1")

    def test_accepts_crlf_and_missing_final_blank_line(self):
        self.assertEqual(updater.openai_deb_checksum(self.record().replace("\n", "\r\n").rstrip(), "26.1.1"), "a" * 64)

    def test_nvchecker_does_not_take_another_packages_version(self):
        config = tomllib.loads((Path(__file__).resolve().parents[1] / "nvchecker.toml").read_text())
        pattern = config["chatgpt-desktop"]["regex"]
        index = self.record() + "\n" + self.record(version="99.1.1", package="other")
        self.assertEqual(re.findall(pattern, index), ["26.1.1"])
        self.assertEqual(re.findall(pattern, "Package: chatgpt\nArchitecture: amd64\n\n" + self.record(package="other")), [])
