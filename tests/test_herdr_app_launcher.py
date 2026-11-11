import os
from pathlib import Path
import subprocess
import unittest


class HerdrAppLauncherTests(unittest.TestCase):
    def launch(self, environment, arguments=()):
        # Substitute only the final executable so tests cannot open the real app.
        launcher = (Path(__file__).resolve().parents[1] / "packages/herdr-app/herdr-app-launcher").read_text()
        self.assertIn("exec /usr/lib/herdr-app/herdr-app ", launcher)
        launcher = launcher.replace("exec /usr/lib/herdr-app/herdr-app ",
                                    """printf '%s\\n' "${HERDR_TELEMETRY-unset}" """)
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
