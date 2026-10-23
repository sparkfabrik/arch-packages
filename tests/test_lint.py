import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("lint", Path(__file__).resolve().parents[1] / "scripts/lint.py")
lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint)


class NamcapAllowTests(unittest.TestCase):
    def check_lint(self, entries, output, returncode=0):
        captured = io.StringIO()
        with patch.object(lint.pathlib.Path, "exists", return_value=True), \
                patch.object(lint.pathlib.Path, "read_text", return_value=entries), \
                patch.object(lint.sys, "argv", ["lint.py", "namcap.allow", "package.pkg.tar.zst"]), \
                patch.object(lint.subprocess, "run", return_value=subprocess.CompletedProcess([], returncode, output)), \
                contextlib.redirect_stdout(captured), self.assertRaises(SystemExit) as exit:
            lint.main()
        return exit.exception.code, captured.getvalue()

    def test_exact_line_and_normalized_file_order(self):
        entry = "pkg W: Referenced library 'libx.so' is an uninstalled dependency (needed in files ['a', 'b'])"
        code, output = self.check_lint(entry, entry.replace("['a', 'b']", "['b', 'a']"))
        self.assertEqual(code, 0)
        self.assertIn("1 warnings; 1 matched exact; 0 matched patterns; passed", output)

    def test_vendored_version_pattern(self):
        entry = "pkg W: ELF file ('usr/lib/vendor/sharp-linux-x64-*.node') lacks PIE."
        for version in ("0.35.4", "0.35.5", ""):
            with self.subTest(version=version):
                code, output = self.check_lint(entry, entry.replace("*", version))
                self.assertEqual(code, 0)
                self.assertIn("0 matched exact; 1 matched patterns", output)

    def test_file_list_pattern(self):
        entry = "pkg W: Referenced python module 'PIL.Image' is an uninstalled dependency (needed in files *)"
        code, output = self.check_lint(entry, entry.replace("*", "['z.py', 'a.py']"))
        self.assertEqual(code, 0)
        self.assertIn("1 matched patterns", output)

    def test_only_star_is_special(self):
        entry = "pkg W: path [linux](module)+?.so|^$\\file-*"
        self.assertEqual(self.check_lint(entry, entry.replace("*", "1.2"))[0], 0)
        for changed in (entry.replace("[linux]", "l"), entry.replace("(module)", "module"), entry.replace("?.", "xZ")):
            with self.subTest(changed=changed):
                self.assertEqual(self.check_lint(entry, changed.replace("*", "1.2"))[0], 1)

    def test_unmatched_warning_and_changed_meaning_fail(self):
        entry = "pkg W: ELF file ('sharp-linux-x64-*.node') lacks PIE."
        for warning in (entry.replace("pkg W:", "other W:"), entry.replace("lacks PIE", "is unstripped"),
                        "prefix " + entry, entry + " suffix", "pkg W: An unrelated warning"):
            with self.subTest(warning=warning):
                code, output = self.check_lint(entry, warning.replace("*", "0.35.5"))
                self.assertEqual(code, 1)
                self.assertIn("FAILED", output)

    def test_errors_and_nonzero_namcap_status_always_fail(self):
        self.assertEqual(self.check_lint("pkg E: *", "pkg E: An error")[0], 1)
        self.assertEqual(self.check_lint("pkg E: An error", "pkg E: An error")[0], 1)
        self.assertEqual(self.check_lint("pkg W: reviewed", "pkg W: reviewed", returncode=1)[0], 1)

    def test_counts_prioritize_exact_and_allow_unused_entries(self):
        entries = "# reason\n\npkg W: exact\npkg W: *\npkg W: unused"
        code, output = self.check_lint(entries, "pkg W: exact\npkg W: changing")
        self.assertEqual(code, 0)
        self.assertIn("2 warnings; 1 matched exact; 1 matched patterns; passed", output)


if __name__ == "__main__":
    unittest.main()
