import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from tests.helpers import temporary_project


class UpdateTests(unittest.TestCase):
    def test_module_update_help_works_outside_checkout_without_scripts_on_path(self):
        source = Path(__file__).resolve().parents[1]
        script = "import runpy,sys; sys.path.insert(0,sys.argv[1]); sys.argv=['harness','update','--help']; runpy.run_module('harness',run_name='__main__')"
        result = subprocess.run([sys.executable, "-I", "-c", script, str(source)],
                                cwd=source.parent, capture_output=True, text=True,
                                env={**os.environ, "PATH": ""})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("update", result.stdout)

    def test_runner_update_dispatches_without_discovering_a_project(self):
        from harness.runner import main
        with patch("harness.updater.main", return_value=0) as update:
            self.assertEqual(main(["update"]), 0)
        update.assert_called_once_with([])

    def test_source_update_pulls_then_reinstalls_with_same_python(self):
        from harness.updater import update_app
        with temporary_project() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            with patch("harness.updater._installation", return_value=(root, True, True)), \
                    patch("harness.updater._run") as run:
                update_app()
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(commands[0], ["git", "-C", str(root), "pull", "--ff-only"])
            self.assertEqual(commands[1][:4], [sys.executable, "-m", "pip", "install"])
            self.assertIn("--user", commands[1])
            self.assertEqual(commands[1][-2:], ["--editable", str(root)])

    def test_remote_update_reinstalls_even_if_version_has_not_changed(self):
        from harness.updater import REPOSITORY, update_app
        with patch("harness.updater._installation", return_value=(None, False, False)), \
                patch("harness.updater._run") as run:
            update_app()
        command = run.call_args.args[0]
        self.assertEqual(command[:4], [sys.executable, "-m", "pip", "install"])
        self.assertIn("--force-reinstall", command)
        self.assertNotIn("--user", command)
        self.assertEqual(command[-1], REPOSITORY)

    def test_failed_pull_does_not_install_or_report_success(self):
        from harness.updater import main
        from harness.updater import UpdateError
        output = io.StringIO()
        with patch("harness.updater._installation", return_value=(Path.cwd(), True, False)), \
                patch("harness.updater._run", side_effect=UpdateError("conflict")) as run, \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertNotEqual(main([]), 0)
        self.assertEqual(run.call_count, 1)
        self.assertNotIn("concluída", output.getvalue())
        self.assertIn("conflict", output.getvalue())

    def test_pip_failure_returns_nonzero(self):
        from harness.updater import main, UpdateError
        with patch("harness.updater._installation", return_value=(None, False, False)), \
                patch("harness.updater._run", side_effect=UpdateError("pip failed")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertNotEqual(main([]), 0)

    def test_pull_uses_real_upstream_and_preserves_local_work(self):
        from harness.updater import update_app, _run
        with temporary_project() as directory:
            root = Path(directory)
            upstream, checkout = root / "upstream", root / "installed app"

            def git(*args):
                result = subprocess.run(["git", *map(str, args)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

            git("init", upstream)
            git("-C", upstream, "config", "user.name", "Test")
            git("-C", upstream, "config", "user.email", "test@example.invalid")
            (upstream / "app.txt").write_text("old")
            git("-C", upstream, "add", ".")
            git("-C", upstream, "commit", "-m", "initial")
            git("clone", upstream, checkout)
            (checkout / "local.txt").write_text("keep me")
            (upstream / "app.txt").write_text("new")
            git("-C", upstream, "commit", "-am", "update")
            commands = []

            def run(command):
                commands.append(command)
                if command[0] == "git":
                    _run(command)
                else:
                    self.assertEqual((checkout / "app.txt").read_text(), "new")

            with patch("harness.updater._installation", return_value=(checkout, True, False)), \
                    patch("harness.updater._run", side_effect=run):
                update_app()
            self.assertEqual(len(commands), 2)
            self.assertEqual((checkout / "local.txt").read_text(), "keep me")

            # A second update must stop rather than overwrite a tracked edit.
            (checkout / "app.txt").write_text("my customization")
            (upstream / "app.txt").write_text("another update")
            git("-C", upstream, "commit", "-am", "conflicting update")
            commands.clear()
            from harness.updater import UpdateError
            with patch("harness.updater._installation", return_value=(checkout, True, False)), \
                    patch("harness.updater._run", side_effect=run), self.assertRaises(UpdateError):
                update_app()
            self.assertEqual(len(commands), 1, "pip must not run after a conflicting pull")
            self.assertEqual((checkout / "app.txt").read_text(), "my customization")

    def test_user_installation_is_preserved_despite_checkout_egg_info(self):
        from harness import updater
        root = Path(updater.__file__).resolve().parent.parent
        installed = Mock()
        installed.metadata = {"Name": updater.PACKAGE}
        installed.locate_file.return_value = root / "user-site"
        checkout = Mock()
        checkout.locate_file.return_value = root
        with patch("harness.updater.metadata.distribution", return_value=checkout), \
                patch("harness.updater.metadata.distributions", return_value=[installed]), \
                patch("harness.updater.site.USER_SITE", str(root / "user-site")), \
                patch("harness.updater.sys.prefix", "python"), \
                patch("harness.updater.sys.base_prefix", "python"):
            self.assertEqual(updater._installation(), (root, True, True))

    def test_virtual_environment_never_requests_user_install(self):
        from harness import updater
        dist = Mock()
        dist.locate_file.return_value = "user-site"
        with patch("harness.updater.metadata.distribution", return_value=dist), \
                patch("harness.updater.sys.prefix", "venv"), \
                patch("harness.updater.sys.base_prefix", "python"):
            self.assertFalse(updater._installation()[2])

    def test_installed_vcs_retains_its_repository(self):
        from harness import updater
        dist = Mock()
        dist.locate_file.return_value = Path.cwd() / "site"
        dist.read_text.return_value = json.dumps({"url": "https://example.invalid/fork.git", "vcs_info": {"vcs": "git", "requested_revision": "develop"}})
        with patch("harness.updater.metadata.distribution", return_value=dist), \
                patch("harness.updater._source", return_value=False):
            source, editable, _ = updater._installation()
        self.assertEqual(source, "git+https://example.invalid/fork.git@develop")
        self.assertFalse(editable)

    def test_windows_launcher_explains_the_single_command_without_starting_pip(self):
        from harness.runner import main
        output = io.StringIO()
        with patch("harness.runner.os.name", "nt"), \
                patch("harness.runner.sys.argv", ["C:/Scripts/harness.exe", "update"]), \
                patch("harness.updater.main") as update, contextlib.redirect_stderr(output):
            self.assertEqual(main(["update"]), 2)
        update.assert_not_called()
        self.assertIn("python -m harness update", output.getvalue())

    def test_missing_git_has_actionable_error_and_nonzero_exit(self):
        from harness.updater import main
        output = io.StringIO()
        with patch("harness.updater._installation", return_value=(Path.cwd(), True, False)), \
                patch("harness.updater.subprocess.run", side_effect=FileNotFoundError), \
                contextlib.redirect_stderr(output):
            self.assertEqual(main([]), 2)
        self.assertIn("git", output.getvalue())


if __name__ == "__main__":
    unittest.main()
