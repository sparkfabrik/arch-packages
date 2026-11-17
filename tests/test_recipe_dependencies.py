import os
from pathlib import Path
import tempfile
import unittest
from test_repository import repository


class RecipeDependencyTests(unittest.TestCase):
    def setUp(self):
        self.old_cwd = os.getcwd()
        self.dir = tempfile.TemporaryDirectory()
        os.chdir(self.dir.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.dir.cleanup()

    def recipe(self, name, distribution="local", *depends, key="depends"):
        path = Path("packages") / name
        path.mkdir(parents=True)
        (path / "PKGBUILD").write_text(f"pkgname={name}\n")
        (path / "distribution").write_text(distribution + "\n")
        lines = [f"pkgbase = {name}", "\tpkgver = 1", *(f"\t{key} = {item}" for item in depends), "", f"pkgname = {name}"]
        (path / ".SRCINFO").write_text("\n".join(lines) + "\n")

    def test_lists_direct_recipe_dependencies_without_version_constraints(self):
        self.recipe("core", "local", "glibc")
        self.recipe("lib", "local")
        self.recipe("app", "local", "core>=0.1.11", "gtk3", "lib")
        self.recipe("tool", "local", "app")
        self.assertEqual(repository.recipe_dependencies("app"), ["core", "lib"])
        self.assertEqual(repository.recipe_dependencies("tool"), ["app"])
        self.assertEqual(repository.recipe_dependencies("core"), [])

    def test_build_dependencies_count(self):
        self.recipe("core", "local")
        self.recipe("app", "local", "core", key="makedepends_x86_64")
        self.assertEqual(repository.recipe_dependencies("app"), ["core"])

    def test_prefix_names_are_not_dependencies(self):
        self.recipe("core", "local")
        self.recipe("app", "local", "core-extra", "libcore")
        self.assertEqual(repository.recipe_dependencies("app"), [])

    def test_published_package_cannot_depend_on_a_recipe(self):
        for mode in ["local", "repository"]:
            with self.subTest(dependency=mode):
                self.recipe("core", mode)
                self.recipe("app", "repository", "core=1")
                with self.assertRaisesRegex(ValueError, "Published package app"):
                    repository.recipe_dependencies("app")
                for name in ["core", "app"]:
                    for item in (Path("packages") / name).iterdir():
                        item.unlink()
                    (Path("packages") / name).rmdir()

    def test_published_dependency_deep_in_the_tree_is_refused(self):
        self.recipe("base", "local")
        self.recipe("core", "repository", "base")
        self.recipe("app", "local", "core")
        with self.assertRaisesRegex(ValueError, "Published package core"):
            repository.recipe_dependencies("app")

    def test_cycles_and_unknown_recipes_fail(self):
        self.recipe("a", "local", "b")
        self.recipe("b", "local", "a")
        self.recipe("self", "local", "self")
        for name in ["a", "self"]:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "cycle"):
                repository.recipe_dependencies(name)
        with self.assertRaises(ValueError):
            repository.recipe_dependencies("missing")
