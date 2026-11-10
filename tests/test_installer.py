import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from harness import __version__
from harness.config import ConfigError, load_config
from harness.installer import init_project, install_skills
from tests.helpers import directory_link, temporary_project


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_project()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_json(self, name, data):
        (self.root / name).write_text(json.dumps(data), encoding="utf-8")

    def test_controls_are_centralized(self):
        init_project(self.root)
        for name in ('harness.json', 'planos/instrucoes.md', 'memoria/decisoes.md'):
            self.assertTrue((self.root / '.harness' / name).is_file())
        self.assertFalse((self.root / 'planos').exists())
        self.assertFalse((self.root / 'memoria').exists())

    def test_empty_repository_and_idempotence(self):
        summary = init_project(self.root)
        config = load_config(self.root)
        self.assertTrue(summary["valid"])
        self.assertFalse(summary["checks_executed"])
        self.assertTrue(all(c["state"] == "unconfigured" for c in config["checks"].values()))
        for path in ("AGENTS.md", ".harness/harness.json", ".harness/planos/instrucoes.md", ".harness/planos/pendencias.md", ".harness/planos/relatorios.md", ".gitignore"):
            self.assertTrue((self.root / path).is_file())
        self.assertTrue((self.root / ".harness/results").is_dir())
        self.assertFalse((self.root / ".harness/http").exists())
        self.assertFalse((self.root / "tarefas").exists())
        self.assertFalse((self.root / "templates").exists())
        self.assertFalse((self.root / "planos/novo-mapa.md").exists())
        self.assertFalse((self.root / "planos/mapa.md").exists())
        self.assertFalse((self.root / "harness/runner.py").exists())
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(init_project(self.root)["created"], [])
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_existing_node_project_detects_real_scripts_without_running(self):
        self.write_json("package.json", {"name": "example", "packageManager": "pnpm@9.0.0", "dependencies": {"react": "1"},
                                        "scripts": {"test": "node test.js", "lint": "eslint .", "prepare": "touch forbidden"}})
        summary = init_project(self.root)
        checks = load_config(self.root)["checks"]
        self.assertEqual(checks["test"]["command"], ["pnpm", "run", "test"])
        self.assertEqual(checks["lint"]["state"], "configured")
        self.assertEqual(checks["build"]["state"], "unconfigured")
        self.assertEqual(checks["prepare"]["state"], "unconfigured")
        self.assertIn("react", summary["inspection"]["frameworks"])
        self.assertFalse((self.root / "forbidden").exists())

    def test_ambiguous_managers_and_placeholder_test_stay_pending(self):
        self.write_json("package.json", {"scripts": {"test": 'echo "Error: no test specified" && exit 1', "lint": "eslint ."}})
        (self.root / "yarn.lock").touch()
        (self.root / "pnpm-lock.yaml").touch()
        init_project(self.root)
        self.assertTrue(all(c["state"] == "unconfigured" for c in load_config(self.root)["checks"].values()))

    def test_python_tool_configuration_and_make_targets(self):
        (self.root / "pyproject.toml").write_text('[project]\nname="sample"\nversion="1"\n[tool.pytest.ini_options]\ntestpaths=["tests"]\n[tool.ruff]\nline-length=88\n', encoding="utf-8")
        (self.root / "Makefile").write_text("build:\n\t@echo built\n", encoding="utf-8")
        checks = init_project(self.root)["configured"]
        self.assertIn("test", checks)
        config = load_config(self.root)["checks"]
        self.assertEqual(config["test"]["command"], ["python", "-m", "pytest"])
        self.assertEqual(config["build"]["command"], ["make", "build"])

    def test_unknown_stack_remains_valid_and_pending(self):
        (self.root / "go.mod").write_text("module example.org/foo\n", encoding="utf-8")
        summary = init_project(self.root)
        self.assertIn("Go", summary["inspection"]["languages"])
        self.assertEqual(summary["configured"], [])

    def test_preserves_instructions_plans_tasks_config_and_gitignore(self):
        (self.root / "planos").mkdir()
        contents = {"AGENTS.md": "Keep my rules", "planos/instrucoes.md": "Real instructions", "planos/pendencias.md": "Known problem", "planos/relatorios.md": "Actual reports"}
        for name, content in contents.items():
            (self.root / name).write_text(content, encoding="utf-8")
        original = {"schema_version": 1, "harness_version": __version__, "project": "mine", "checks": {}}
        self.write_json("harness.json", original)
        original_bytes = (self.root / "harness.json").read_bytes()
        (self.root / ".gitignore").write_bytes(b"local-data\r\n")
        summary = init_project(self.root)
        for name, content in contents.items():
            self.assertEqual((self.root / name).read_text(encoding="utf-8"), content)
        self.assertEqual((self.root / "harness.json").read_bytes(), original_bytes)
        self.assertTrue((self.root / ".gitignore").read_bytes().startswith(b"local-data\r\n"))
        self.assertIn("AGENTS.md", summary["differences"])
        self.assertIn("harness.json", summary["legacy_files"])
        self.assertFalse((self.root / ".harness/harness.json").exists())

    def test_preserves_legacy_control_files_without_silent_migration(self):
        (self.root / "planos").mkdir()
        (self.root / "tarefas").mkdir()
        old_plan = self.root / "planos/novo-mapa.md"
        old_pending = self.root / "tarefas/pendencias.md"
        old_plan.write_text("previous instructions", encoding="utf-8")
        old_pending.write_text("previous pending work", encoding="utf-8")
        summary = init_project(self.root)
        self.assertEqual(old_plan.read_text(encoding="utf-8"), "previous instructions")
        self.assertEqual(old_pending.read_text(encoding="utf-8"), "previous pending work")
        self.assertEqual(set(summary["legacy_files"]), {"planos", "tarefas/pendencias.md"})
        self.assertFalse((self.root / ".harness/planos").exists())

    def test_control_file_path_conflict_causes_no_partial_install(self):
        (self.root / ".harness/planos/relatorios.md").mkdir(parents=True)
        with self.assertRaises(ConfigError):
            init_project(self.root)
        self.assertFalse((self.root / "harness.json").exists())
        self.assertFalse((self.root / "planos/instrucoes.md").exists())

    def test_invalid_existing_config_causes_no_partial_install(self):
        (self.root / "harness.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ConfigError):
            init_project(self.root)
        self.assertEqual([p.name for p in self.root.iterdir()], ["harness.json"])

    def test_conflicting_file_in_directory_position_causes_no_partial_install(self):
        (self.root / ".harness").mkdir()
        (self.root / ".harness/planos").write_text("important file", encoding="utf-8")
        with self.assertRaises(ConfigError):
            init_project(self.root)
        self.assertFalse((self.root / "harness.json").exists())

    def test_invalid_path(self):
        with self.assertRaises(ConfigError):
            init_project(self.root / "absent")

    def test_malformed_manifest_does_not_trigger_partial_install(self):
        (self.root / "package.json").write_text("{", encoding="utf-8")
        with self.assertRaises(ConfigError):
            init_project(self.root)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_skills_are_explicit_and_updates_back_up_existing_content(self):
        destination = self.root / "codex-skills"
        self.assertFalse(destination.exists())
        init_project(self.root)
        self.assertFalse(destination.exists())
        first = install_skills(destination)
        self.assertEqual(len(first["created"]), 5)
        target = destination / "code-investigation" / "SKILL.md"
        target.write_text("my custom skill", encoding="utf-8")
        extra = target.parent / "extra.md"
        extra.write_text("keep", encoding="utf-8")
        self.assertEqual(install_skills(destination)["conflicts"], ["code-investigation"])
        self.assertEqual(target.read_text(encoding="utf-8"), "my custom skill")
        summary = install_skills(destination, update=True)
        self.assertEqual(summary["updated"], ["code-investigation"])
        backup = Path(summary["backups"][0])
        self.assertEqual(backup.read_text(encoding="utf-8"), "my custom skill")
        self.assertEqual(extra.read_text(encoding="utf-8"), "keep")

    def test_default_skill_destination_is_agents_skills_in_user_home(self):
        with patch("harness.installer.Path.home", return_value=self.root):
            summary = install_skills()
        self.assertEqual(Path(summary["destination"]), self.root / ".agents" / "skills")
        self.assertEqual(len(summary["created"]), 5)
        self.assertFalse((self.root / ".codex").exists())

    def test_explicit_skill_source_and_missing_source_preserve_destination(self):
        source = self.root / "source-skills"
        source.mkdir()
        names = ("verified-development", "code-investigation", "tdd-implementation", "adversarial-review", "http-homologation")
        for name in names:
            (source / name).mkdir()
            (source / name / "SKILL.md").write_text(f"Independent source for {name}", encoding="utf-8")
        destination = self.root / "destination-skills"
        summary = install_skills(destination, source=source)
        self.assertEqual(len(summary["created"]), 5)
        self.assertEqual((destination / names[0] / "SKILL.md").read_text(encoding="utf-8"), f"Independent source for {names[0]}")
        missing_destination = self.root / "not-created"
        with self.assertRaises(ConfigError):
            install_skills(missing_destination, source=self.root / "missing")
        self.assertFalse(missing_destination.exists())

    def test_setup_entry_point(self):
        result = subprocess.run([sys.executable, "setup.py", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(load_config(self.root))

    def test_gitignore_negation_cannot_leave_results_unignored(self):
        (self.root / ".gitignore").write_text(".harness/\n!.harness/\n", encoding="utf-8")
        init_project(self.root)
        self.assertEqual((self.root / ".gitignore").read_text(encoding="utf-8").splitlines()[-1], ".harness/")

    def test_existing_empty_gitignore_is_reported_as_updated(self):
        (self.root / ".gitignore").touch()
        summary = init_project(self.root)
        self.assertIn(".gitignore", summary["updated"])
        self.assertNotIn(".gitignore", summary["created"])

    def test_linked_directory_cannot_modify_external_files(self):
        project = self.root / "project"
        project.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (project / ".harness").mkdir()
        directory_link(project / ".harness/planos", outside)
        with self.assertRaises(ConfigError):
            init_project(project)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((project / "AGENTS.md").exists())

    def test_symlinked_skill_preserves_external_content(self):
        destination = self.root / "skills"
        destination.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        original = outside / "SKILL.md"
        original.write_text("preserve", encoding="utf-8")
        directory_link(destination / "verified-development", outside)
        with self.assertRaises(ConfigError):
            install_skills(destination, update=True)
        self.assertEqual(original.read_text(encoding="utf-8"), "preserve")
