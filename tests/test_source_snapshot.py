import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from harness.config import ConfigError
from harness.source_snapshot import capture, changes, validate_snapshot, _digest
from tests.helpers import directory_link


class SourceSnapshotTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_no_git_includes_unknown_extensions_configs_and_unicode_and_detects_moves(self):
        file = self.root / "ação [1].custom"
        file.write_bytes(b"source input")
        before = capture(self.root)
        self.assertEqual(set(before["files"]), {file.name})
        self.assertEqual(before, capture(self.root))
        file.rename(self.root / "renamed.custom")
        self.assertEqual(changes(before, capture(self.root)), sorted(["renamed.custom", file.name]))
        (self.root / "renamed.custom").unlink()
        self.assertEqual(changes(before, capture(self.root)), [file.name])

    def test_generated_directories_are_not_traversed_and_config_is_included(self):
        for name in ("node_modules", ".git", "build", "dist", "__pycache__", ".harness/results"):
            path = self.root / name
            path.mkdir(parents=True)
            (path / "output.log").write_bytes(b"generated")
        (self.root / ".git/output.log").unlink()
        (self.root / ".git").rmdir()
        config = self.root / ".harness/harness.json"
        config.write_text("{}", encoding="utf-8")
        before = capture(self.root)
        self.assertEqual(set(before["files"]), {".harness/harness.json"})
        (self.root / "build/output.log").write_bytes(b"changed output")
        (self.root / ".harness/results/output.log").write_bytes(b"changed evidence unrelated")
        self.assertEqual(before, capture(self.root))
        config.write_text('{"checks":{}}', encoding="utf-8")
        self.assertEqual(changes(before, capture(self.root)), [".harness/harness.json"])

    def test_real_git_includes_staged_and_unstaged_content_without_commit(self):
        self.git("init", "-q")
        path = self.root / "source.py"
        path.write_bytes(b"first\n")
        self.git("add", "--", "source.py")
        before = capture(self.root)
        path.write_bytes(b"second\n")
        unstaged = capture(self.root)
        self.assertEqual(unstaged["index"], before["index"])
        self.assertEqual(changes(before, unstaged), ["source.py"])
        self.git("add", "--", "source.py")
        path.write_bytes(b"first\n")
        staged = capture(self.root)
        self.assertEqual(staged["files"], before["files"])
        self.assertNotEqual(staged["index"], before["index"])
        self.assertEqual(changes(before, staged), ["source.py"])
        path.unlink()
        self.assertNotIn("source.py", capture(self.root)["files"])

    def test_generated_directory_names_do_not_exclude_regular_source_files(self):
        names = {"build", "dist", "target", "package.egg-info", "scripts/build"}
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"original source")
        before = capture(self.root)
        self.assertEqual(set(before["files"]), names)
        for name in sorted(names):
            with self.subTest(name=name):
                (self.root / name).write_bytes(b"changed source")
                self.assertEqual(changes(before, capture(self.root)), [name])
                (self.root / name).write_bytes(b"original source")
        self.git("init", "-q")
        self.git("add", "--", *sorted(names))
        staged = capture(self.root)
        self.assertEqual(set(staged["files"]), names)
        self.assertEqual(set(staged["index"]), names)

    def test_arbitrary_git_ignored_source_is_still_included(self):
        self.git("init", "-q")
        (self.root / ".gitignore").write_text("secret.conf\n", encoding="utf-8")
        (self.root / "secret.conf").write_bytes(b"source configuration")
        self.assertIn("secret.conf", capture(self.root)["files"])

    def test_source_links_are_refused_and_unknown_scope_and_unsafe_manifests_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        directory_link(self.root / "linked", outside)
        with self.assertRaises(ConfigError):
            capture(self.root)
        self.root.joinpath("linked").rmdir() if not self.root.joinpath("linked").is_symlink() else self.root.joinpath("linked").unlink()
        original = capture(self.root)
        for mutate in (lambda data: data.update(scope="agent-selected-list"),
                       lambda data: data["files"].update({"../escape.py": "0" * 64}),
                       lambda data: data["files"].update({"build/hidden.py": "0" * 64}),
                       lambda data: data.update(sha256="0" * 64)):
            data = json.loads(json.dumps(original))
            mutate(data)
            with self.assertRaises(ConfigError):
                validate_snapshot(data)

    def test_unreadable_source_and_source_changes_during_scan_never_become_empty_success(self):
        source = self.root / "app.py"
        source.write_bytes(b"original")
        with patch.object(Path, "open", side_effect=PermissionError("Unreadable source")):
            with self.assertRaisesRegex(ConfigError, "Cannot inspect source"):
                capture(self.root)
        original_open = Path.open

        def mutate(path, *args, **kwargs):
            if path == source and args == ("rb",):
                with original_open(path, "wb") as stream:
                    stream.write(b"changed during scan")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", mutate):
            with self.assertRaisesRegex(ConfigError, "Source changed"):
                capture(self.root)
