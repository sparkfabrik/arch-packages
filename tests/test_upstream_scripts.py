import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_repository import load

scripts = load("upstream_scripts")
URL = "https://example.com/install.sh"


class UpstreamScriptTests(unittest.TestCase):
    def setUp(self):
        self.old_cwd = os.getcwd()
        self.dir = tempfile.TemporaryDirectory()
        os.chdir(self.dir.name)
        Path("packages/example").mkdir(parents=True)
        Path("upstream-scripts.toml").write_text(f'[example]\nurl = "{URL}"\n')
        Path("packages/example/upstream-install.reviewed.sh").write_bytes(b"#!/bin/sh\necho reviewed\n")
        self.env = patch.dict(os.environ, {"GITHUB_OUTPUT": str(Path(self.dir.name) / "output")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        os.chdir(self.old_cwd)
        self.dir.cleanup()

    def run_check(self, upstream, *args):
        with patch.object(scripts, "fetch", return_value=upstream) as fetch, \
                patch("sys.stdout") as stdout, patch("sys.stderr"):
            code = scripts.main(["check", *args])
        printed = "".join(call.args[0] for call in stdout.write.call_args_list)
        return code, printed, fetch

    def test_unchanged_script_passes(self):
        code, printed, fetch = self.run_check(b"#!/bin/sh\necho reviewed\n", "--markdown", "body.md")
        self.assertEqual(code, 0)
        self.assertEqual(printed, "")
        self.assertFalse(Path("body.md").exists())
        fetch.assert_called_once_with(URL)
        self.assertEqual(Path("output").read_text(), "changed=false\n")

    def test_changed_script_fails_with_a_diff(self):
        code, printed, _ = self.run_check(b"#!/bin/sh\necho changed\n", "--markdown", "body.md", "example")
        self.assertEqual(code, 1)
        self.assertIn("-echo reviewed\n+echo changed\n", printed)
        self.assertIn("--- a/packages/example/upstream-install.reviewed.sh", printed)
        self.assertIn("+echo changed", Path("body.md").read_text())
        self.assertEqual(Path("output").read_text(), "changed=true\n")

    def test_invisible_byte_changes_are_reported(self):
        code, printed, _ = self.run_check(b"#!/bin/sh\necho reviewed\n\xff")
        self.assertEqual(code, 1)
        self.assertIn("No newline at end of file", printed)
        code, printed, _ = self.run_check(b"#!/bin/sh\r\necho reviewed\n")
        self.assertEqual(code, 1)

    def test_markdown_fence_cannot_be_closed_by_upstream_text(self):
        section = scripts.markdown("example", URL, "+echo ``````\n")
        self.assertIn("\n```````diff\n", section)
        self.assertTrue(section.endswith("\n```````\n"))

    def test_markdown_is_truncated(self):
        section = scripts.markdown("example", URL, "+" + "x" * (scripts.MAX_MARKDOWN * 2) + "\n")
        self.assertLess(len(section), scripts.MAX_MARKDOWN + 1000)
        self.assertIn("[diff truncated", section)

    def test_unlisted_packages_fail_unless_allowed(self):
        with self.assertRaises(SystemExit):
            self.run_check(b"", "other")
        code, printed, fetch = self.run_check(b"", "--allow-unlisted", "other")
        self.assertEqual((code, printed), (0, ""))
        fetch.assert_not_called()

    def test_check_prints_the_sha256_that_accept_requires(self):
        upstream = b"#!/bin/sh\necho changed\n"
        with patch.object(scripts, "fetch", return_value=upstream), \
                patch("sys.stdout"), patch("sys.stderr") as stderr:
            scripts.main(["check", "example"])
        printed = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertIn(f"example: upstream sha256 {hashlib.sha256(upstream).hexdigest()}", printed)

    def test_accept_stores_the_exact_reviewed_bytes(self):
        upstream = b"#!/bin/sh\r\necho new\n\xff"
        digest = hashlib.sha256(upstream).hexdigest()
        with patch.object(scripts, "fetch", return_value=upstream), patch("sys.stdout"):
            self.assertEqual(scripts.main(["accept", "example", "--sha256", digest.upper()]), 0)
        self.assertEqual(Path("packages/example/upstream-install.reviewed.sh").read_bytes(), upstream)

    def test_accept_refuses_bytes_that_were_not_reviewed(self):
        reviewed = hashlib.sha256(b"#!/bin/sh\necho reviewed later\n").hexdigest()
        path = Path("packages/example/upstream-install.reviewed.sh")
        before = path.read_bytes()
        for digest in [reviewed, "0" * 63, "g" * 64]:
            with self.subTest(digest=digest), \
                    patch.object(scripts, "fetch", return_value=b"#!/bin/sh\necho swapped\n"), \
                    self.assertRaises(SystemExit):
                scripts.main(["accept", "example", "--sha256", digest])
            self.assertEqual(path.read_bytes(), before)
        with patch("sys.stderr"), self.assertRaises(SystemExit):
            scripts.main(["accept", "example"])

    def test_version_prs_selects_every_version_branch_of_the_package(self):
        pulls = [{"number": 1, "headRefName": "chore/update-example-0.1.21"},
                 {"number": 2, "headRefName": "chore/update-example-0.1.22"},
                 {"number": 3, "headRefName": "chore/update-example-extra-1.0"},
                 {"number": 4, "headRefName": "feat/example-0.1.23"},
                 {"number": 5, "headRefName": "chore/update-example-"},
                 {"number": 6, "headRefName": "chore/update-other-1.0"}]
        self.assertEqual(scripts.version_prs("example", pulls), [1, 2])

    def test_config_accepts_only_plain_https_urls(self):
        for text in ['[example]\nurl = "http://example.com/a.sh"\n',
                     '[example]\nurl = "https://example.com/a.sh?x=1"\n',
                     '[example]\nurl = "https://example.com/a.sh"\npath = "../x"\n',
                     '["../x"]\nurl = "https://example.com/a.sh"\n',
                     'example = "https://example.com/a.sh"\n']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                scripts.entries(text)

    def test_repository_config_has_a_reviewed_copy_for_every_entry(self):
        root = Path(__file__).resolve().parents[1]
        for package in scripts.entries((root / scripts.CONFIG).read_text()):
            with self.subTest(package=package):
                self.assertTrue((root / scripts.reviewed_path(package)).is_file())
