import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class LauncherTests(unittest.TestCase):
    def launch(self, environment, arguments=(), config=""):
        # Substitute only the final executable so tests cannot open the real app.
        launcher = (Path(__file__).resolve().parents[1] / "packages/chatgpt-desktop/chatgpt-launcher").read_text()
        launcher = launcher.replace('exec /usr/lib/chatgpt/ChatGPT', "printf '%s\\n'")
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "codex-flags.conf").write_text(config)
            env = {**os.environ, "XDG_CONFIG_HOME": directory, "WAYLAND_DISPLAY": "", "XDG_SESSION_TYPE": "x11", **environment}
            result = subprocess.check_output(["bash", "-c", launcher, "launcher", *arguments], env=env, text=True)
        return result.splitlines()

    def test_wayland_auto_detection(self):
        for env in [{"WAYLAND_DISPLAY": "wayland-1"}, {"XDG_SESSION_TYPE": "wayland"}]:
            self.assertEqual(self.launch(env, ["--test"]), ["--ozone-platform=wayland", "--test"])

    def test_x11_is_unchanged(self):
        self.assertEqual(self.launch({}, ["--test"]), ["--test"])

    def test_explicit_platform_and_hint_override_detection(self):
        for args in [["--ozone-platform=x11"], ["--ozone-platform", "x11"], ["--ozone-platform-hint=auto"]]:
            self.assertEqual(self.launch({"WAYLAND_DISPLAY": "wayland-1"}, args), args)

    def test_config_flags_are_literal_and_override_detection(self):
        flags = self.launch({"WAYLAND_DISPLAY": "wayland-1"}, ["--test"], "# comment\n\n--ozone-platform=x11\n--example=$(false) # inline comment\n")
        self.assertEqual(flags, ["--ozone-platform=x11", "--example=$(false)", "--test"])
