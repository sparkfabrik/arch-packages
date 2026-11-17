import os
from pathlib import Path
import shlex
import subprocess
import sys
import unittest

# Stands in for the app: a separate process that prints the HERDR_TELEMETRY it
# inherited, then its arguments, so an unexported variable reads as "unset".
CHILD = 'import os, sys; print("\\n".join([os.environ.get("HERDR_TELEMETRY", "unset"), *sys.argv[1:]]))'


class HerdrAppLauncherTests(unittest.TestCase):
    def launch(self, environment, arguments=()):
        # Substitute only the final executable so tests cannot open the real app.
        launcher = (Path(__file__).resolve().parents[1] / "packages/herdr-app/herdr-app-launcher").read_text()
        self.assertIn("exec /usr/lib/herdr-app/herdr-app ", launcher)
        child = f"{shlex.quote(sys.executable)} -I -c {shlex.quote(CHILD)}"
        launcher = launcher.replace("exec /usr/lib/herdr-app/herdr-app ", f"exec {child} ")
        env = {key: value for key, value in os.environ.items() if key != "HERDR_TELEMETRY"}
        env.update(environment)
        result = subprocess.check_output(["bash", "-c", launcher, "launcher", *arguments], env=env, text=True)
        return result.splitlines()

    def test_telemetry_is_off_by_default(self):
        self.assertEqual(self.launch({}, ["--test", "a b"]), ["0", "--test", "a b"])
        self.assertEqual(self.launch({"HERDR_TELEMETRY": ""}), ["0"])

    def test_user_choice_is_kept(self):
        for value in ["1", "0", "off"]:
            with self.subTest(value=value):
                self.assertEqual(self.launch({"HERDR_TELEMETRY": value}), [value])
