import json
from pathlib import Path
import unittest

from harness import __version__
from harness.config import ConfigError, load_config
from tests.helpers import directory_link, temporary_project


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_project()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = {
            "schema_version": 1,
            "harness_version": __version__,
            "project": "example",
            "checks": {},
        }

    def write(self):
        (self.root / "harness.json").write_text(json.dumps(self.data), encoding="utf-8")

    def test_valid_configuration_does_not_require_conventional_checks(self):
        self.write()
        self.assertEqual(load_config(self.root), self.data)

    def test_invalid_configurations(self):
        cases = [
            {"schema_version": 2}, {"schema_version": True},
            {"harness_version": ""}, {"project": ""},
            {"extra": True}, {"checks": []},
            {"checks": {"../escape": {"state": "unconfigured", "reason": "pending"}}},
            {"checks": {"x": {"state": "passed"}}},
            {"checks": {"x": {"state": "configured", "command": "echo unsafe"}}},
            {"checks": {"x": {"state": "not_applicable"}}},
            {"checks": {"x": {"state": "unconfigured", "command": ["echo"], "reason": "pending"}}},
            {"checks": {"x": {"state": "configured", "command": ["echo"], "cwd": "../outside", "timeout": 1}}},
            {"checks": {"x": {"state": "configured", "command": ["echo"], "cwd": "\x00", "timeout": 1}}},
            {"checks": {"x": {"state": "configured", "command": [""], "cwd": ".", "timeout": 1}}},
            {"checks": {"x": {"state": "configured", "command": ["echo"], "cwd": ".", "timeout": True}}},
            {"checks": {"x": {"state": "configured", "command": ["echo"], "cwd": ".", "timeout": float("nan")}}},
            {"checks": {"x": {"state": "configured", "command": ["echo"], "cwd": ".", "timeout": 0}}},
            {"checks": {"x": {"state": "configured", "command": ["echo"], "cwd": ".", "timeout": 10**400}}},
            {"checks": {"x": {"state": "configured", "command": ["echo", 1], "cwd": ".", "timeout": 1}}},
        ]
        original = self.data.copy()
        for patch in cases:
            with self.subTest(patch=patch):
                self.data = {**original, **patch}
                self.write()
                with self.assertRaises(ConfigError):
                    load_config(self.root)

    def test_malformed_and_duplicate_json(self):
        for content in ('{', '{"schema_version":1,"schema_version":1}', '[]'):
            (self.root / "harness.json").write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(ConfigError):
                load_config(self.root)

    def test_link_cannot_escape_project_working_directory(self):
        project = self.root / "project"
        project.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        directory_link(project / "linked", outside)
        self.data["checks"] = {"escape": {"state": "configured", "command": ["echo", "x"], "cwd": "linked", "timeout": 1}}
        (project / "harness.json").write_text(json.dumps(self.data), encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_config(project)
