import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness import __version__
from harness.config import ConfigError, load_config
from harness.installer import init_project, install_skills
from harness.project import PROJECT_FILES
from tests.helpers import directory_link, temporary_project


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_json(self, name, data):
        (self.root / name).write_text(json.dumps(data), encoding="utf-8")

    def test_generated_agents_matches_requested_text_exactly(self):
        expected = r"""# AGENTS.md — Regras permanentes

- Para funcionalidades e bugs, use `$verified-development`, com `$code-investigation`, `$tdd-implementation`, `$review-agent` independente e `$http-homologation` quando aplicável.
- Antes de editar: `git status --short`, inspeção dos diffs e investigação do código, testes e convenções. Preserve alterações anteriores e comportamento fora do escopo.
- Antes da primeira tarefa gerenciada, siga a migração descrita em `$verified-development`. Consulte `IMPLEMENTATION_CONSTRAINTS.md`, quando existir.
- Consulte seletivamente regras, decisões e problemas relevantes da memória; confronte-os com o código, investigue divergências e evite repetir investigações confiáveis.
- Peça aprovação para alterações relevantes de arquitetura, contratos públicos, esquema de dados, dependências, segurança ou ações externas.
- Reproduza bugs com testes quando viável; execute verificações pertinentes e confira regressões. Se houver `.harness/harness.json`, consulte `python -m harness.runner --list` e selecione apenas checks configurados via `--check NOME`. Lint e build não são obrigatórios.
- Registre comandos, resultados e falhas. Faça revisão independente quando suportada; senão, informe a limitação. Não declare verificações sem evidências.
- Não faça commits, push ou deploy nem versione `.harness/`. Sem autorização, não use `git add`, `git merge`, migrações, seeders ou scripts destrutivos; não altere serviços externos ou dados persistentes nem amplie o escopo. Não use `git reset` ou `git clean` indiscriminadamente.
- Não crie documentação, automações ou arquivos auxiliares desnecessários.
- Após verificar, registre memória e `.harness/pendencias.md` **somente se a omissão prejudicar trabalho futuro**. Atualize sem duplicar e distinga fatos confirmados, decisões aprovadas e questões abertas.
- Evidências detalhadas ficam em `.harness/results/`; comandos e resultados, no relatório final da sessão, sem cópia automática para Markdown.
- Entregue um resumo na conversa com comportamento, verificações, revisão e limitações.
- Comentários no código somente em PT-BR. Evitá-los a não ser que sejam essenciais para o entendimento do trecho de código.

## Regras permanentes do projeto

Acrescente somente restrições estáveis.
"""
        init_project(self.root)
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), expected.encode("utf-8"))

    def test_controls_are_centralized(self):
        init_project(self.root)
        files = {path.relative_to(self.root).as_posix() for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(files, {
            'AGENTS.md', '.gitignore', '.harness/harness.json', '.harness/pendencias.md',
            '.harness/memoria/regras-negocio.md', '.harness/memoria/decisoes.md',
            '.harness/memoria/problemas-conhecidos.md',
        })
        self.assertEqual(list((self.root / '.harness/results').iterdir()), [])

    def test_empty_repository_and_idempotence(self):
        summary = init_project(self.root)
        config = load_config(self.root)
        self.assertTrue(summary["valid"])
        self.assertFalse(summary["checks_executed"])
        self.assertTrue(all(c["state"] == "unconfigured" for c in config["checks"].values()))
        for path in ("AGENTS.md", ".harness/harness.json", ".harness/pendencias.md", ".gitignore"):
            self.assertTrue((self.root / path).is_file())
        self.assertFalse((self.root / ".harness/planos").exists())
        self.assertTrue((self.root / ".harness/results").is_dir())
        self.assertFalse((self.root / ".harness/http").exists())
        self.assertFalse((self.root / "tarefas").exists())
        self.assertFalse((self.root / "templates").exists())
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

    def test_local_legacy_controls_are_inventoried_without_competing_pending_document(self):
        for index, name in enumerate(('.harness/planos/relatorios.md', '.harness/tarefas/pendencias.md',
                                      'relatorios.md', '.harness/relatorios.md')):
            with self.subTest(name=name):
                project = self.root / str(index)
                original = project / name
                original.parent.mkdir(parents=True)
                original.write_bytes(b'Confirmed finding to preserve.\r\n')
                before = original.read_bytes()
                result = init_project(project)
                expected = '.harness/planos' if name.startswith('.harness/planos/') else name
                self.assertIn(expected, result['legacy_files'])
                self.assertEqual(original.read_bytes(), before)
                self.assertFalse((project / '.harness/pendencias.md').exists())

    def test_control_file_path_conflict_causes_no_partial_install(self):
        (self.root / ".harness/pendencias.md").mkdir(parents=True)
        with self.assertRaises(ConfigError):
            init_project(self.root)
        self.assertFalse((self.root / "harness.json").exists())
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_invalid_existing_config_causes_no_partial_install(self):
        (self.root / "harness.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ConfigError):
            init_project(self.root)
        self.assertEqual([p.name for p in self.root.iterdir()], ["harness.json"])

    def test_conflicting_file_in_directory_position_causes_no_partial_install(self):
        (self.root / ".harness").mkdir()
        (self.root / ".harness/memoria").write_text("important file", encoding="utf-8")
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
        self.assertEqual(set(first["created"]), {
            "verified-development", "code-investigation", "tdd-implementation", "http-homologation",
            "sdd-auto", "sdd-lite", "sdd-full", "sdd-off",
        })
        self.assertEqual({path.name for path in destination.iterdir()}, set(first["created"]))
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
        self.assertEqual(len(summary["created"]), 8)
        self.assertFalse((self.root / ".codex").exists())

    def test_explicit_skill_source_and_missing_source_preserve_destination(self):
        source = self.root / "source-skills"
        source.mkdir()
        names = ("verified-development", "code-investigation", "tdd-implementation", "http-homologation")
        for name in names:
            (source / name).mkdir()
            (source / name / "SKILL.md").write_text(f"Independent source for {name}", encoding="utf-8")
        destination = self.root / "destination-skills"
        summary = install_skills(destination, source=source)
        self.assertEqual(len(summary["created"]), 4)
        self.assertEqual((destination / names[0] / "SKILL.md").read_text(encoding="utf-8"), f"Independent source for {names[0]}")
        missing_destination = self.root / "not-created"
        with self.assertRaises(ConfigError):
            install_skills(missing_destination, source=self.root / "missing")
        self.assertFalse(missing_destination.exists())

    def test_upgrade_installs_mode_skills_and_backs_up_custom_coordinator(self):
        destination = self.root / "skills"
        source = Path(__file__).resolve().parents[1] / "skills"
        coordinator = destination / "verified-development/SKILL.md"
        coordinator.parent.mkdir(parents=True)
        coordinator.write_bytes(b"My locally customized coordinator\r\n")

        upgraded = install_skills(destination, update=True, source=source)

        self.assertEqual(upgraded["updated"], ["verified-development"])
        self.assertEqual(Path(upgraded["backups"][0]).read_bytes(), b"My locally customized coordinator\r\n")
        self.assertEqual(coordinator.read_text(encoding="utf-8"), (source / "verified-development/SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual({name for name in upgraded["created"] if name.startswith("sdd-")}, {
            "sdd-auto", "sdd-lite", "sdd-full", "sdd-off",
        })
        self.assertEqual(install_skills(destination, update=True, source=source)["backups"], [])

    def test_partial_sdd_skill_source_fails_before_installing_any_skills(self):
        source = self.root / "source-skills"
        names = ("verified-development", "code-investigation", "tdd-implementation", "http-homologation", "sdd-lite")
        for name in names:
            target = source / name / "SKILL.md"
            target.parent.mkdir(parents=True)
            target.write_text(f"Skill {name}\n", encoding="utf-8")

        destination = self.root / "destination-skills"
        with self.assertRaisesRegex(ConfigError, "Skill source missing"):
            install_skills(destination, source=source)
        self.assertFalse(destination.exists())

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
        directory_link(project / ".harness/memoria", outside)
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


class InstallerGitProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_project()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")

    def git(self, *args, codes=(0,)):
        result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True)
        self.assertIn(result.returncode, codes, result.stderr.decode(errors="replace"))
        return result.stdout

    def assert_protected(self, project=None):
        project = project or self.root
        for path in (project / ".harness/harness.json", project / ".harness/results/probe.json"):
            self.git("check-ignore", "--", str(path))
        if not self.git("ls-files", "--", str(project / "AGENTS.md")):
            self.git("check-ignore", "--", str(project / "AGENTS.md"))

    def test_tracked_gitignore_and_index_are_unchanged_and_repeat_is_noop(self):
        ignore = self.root / ".gitignore"
        ignore.write_bytes(b"# Company rules\r\n*.tmp\r\n")
        self.git("add", "--", ".gitignore")
        index = (self.root / ".git/index").read_bytes()
        status = self.git("status", "--porcelain", "--untracked-files=all")
        init_project(self.root)
        self.assertEqual(ignore.read_bytes(), b"# Company rules\r\n*.tmp\r\n")
        self.assertEqual((self.root / ".git/index").read_bytes(), index)
        self.assert_protected()
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), status)
        before = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in self.root.rglob("*") if p.is_file()}
        result = init_project(self.root)
        self.assertEqual(result["created"], [])
        self.assertEqual(result["updated"], [])
        self.assertEqual(before, {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns)
                                 for p in self.root.rglob("*") if p.is_file()})

    def test_tracked_agents_are_preserved_and_local_alternative_is_ignored(self):
        agents = self.root / "AGENTS.md"
        agents.write_bytes(b"# Corporate instructions\r\nKeep exactly.\r\n")
        self.git("add", "--", "AGENTS.md")
        index = self.git("ls-files", "--stage")
        status = self.git("status", "--porcelain", "--untracked-files=all")
        init_project(self.root)
        self.assertEqual(agents.read_bytes(), b"# Corporate instructions\r\nKeep exactly.\r\n")
        self.assertEqual((self.root / ".harness/AGENTS.md").read_bytes(), PROJECT_FILES["AGENTS.md"].encode())
        self.assertEqual(self.git("ls-files", "--stage"), index)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), status)
        self.assert_protected()

    def test_untracked_instructions_and_ignore_are_preserved(self):
        (self.root / "AGENTS.md").write_bytes(b"Local rules\r\n")
        (self.root / ".gitignore").write_bytes(b"*.tmp\r\n")
        init_project(self.root)
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), b"Local rules\r\n")
        self.assertEqual((self.root / ".gitignore").read_bytes(), b"*.tmp\r\n")
        self.assert_protected()
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), b"?? .gitignore\n")

    def test_tracked_local_alternative_aborts_before_mutations(self):
        (self.root / "AGENTS.md").write_bytes(b"Corporate root instructions\n")
        (self.root / ".harness").mkdir()
        (self.root / ".harness/AGENTS.md").write_bytes(b"Corporate nested instructions\n")
        self.git("add", "--", "AGENTS.md", ".harness/AGENTS.md")
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(ConfigError, "prevents local harness instructions"):
            init_project(self.root)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes()
                                 for p in self.root.rglob("*") if p.is_file()})

    def test_tracked_negation_aborts_before_creating_controls(self):
        for pattern in (b"!.harness/\n", b"!AGENTS.md\n"):
            with self.subTest(pattern=pattern):
                (self.root / ".gitignore").write_bytes(pattern)
                self.git("add", "--", ".gitignore")
                exclude = (self.root / ".git/info/exclude").read_bytes()
                with self.assertRaisesRegex(ConfigError, "ignore (rule exposes|verification failed)"):
                    init_project(self.root)
                self.assertFalse((self.root / "AGENTS.md").exists())
                self.assertFalse((self.root / ".harness").exists())
                self.assertEqual((self.root / ".gitignore").read_bytes(), pattern)
                self.assertEqual((self.root / ".git/info/exclude").read_bytes(), exclude)

    def test_nested_projects_use_local_untracked_ignore_without_exposing_it(self):
        for name in ("nested", "path with spaces/ação[1]"):
            with self.subTest(name=name):
                project = self.root / name
                project.mkdir(parents=True)
                ignore = project / ".gitignore"
                ignore.write_bytes(b"*.tmp\n")
                exclude = (self.root / ".git/info/exclude").read_bytes()
                init_project(project)
                self.assert_protected(project)
                self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), b"")
                self.assertEqual((self.root / ".git/info/exclude").read_bytes(), exclude)
                self.assertTrue(ignore.read_bytes().startswith(b"*.tmp\n"))

    def test_nested_tracked_ignore_fails_safely_when_local_exclusion_is_unavailable(self):
        project = self.root / "nested"
        project.mkdir()
        ignore = project / ".gitignore"
        ignore.write_bytes(b"*.tmp\n")
        self.git("add", "--", "nested/.gitignore")
        with self.assertRaises(ConfigError):
            init_project(project)
        self.assertEqual(ignore.read_bytes(), b"*.tmp\n")
        self.assertFalse((project / ".harness").exists())
        self.assertFalse((project / "AGENTS.md").exists())

    def test_path_conflict_is_detected_before_ignore_changes(self):
        (self.root / ".harness").mkdir()
        (self.root / ".harness/results").write_bytes(b"Keep conflict")
        exclude = (self.root / ".git/info/exclude").read_bytes()
        with self.assertRaises(ConfigError):
            init_project(self.root)
        self.assertEqual((self.root / ".git/info/exclude").read_bytes(), exclude)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_linked_exclude_directory_is_rejected_without_touching_target(self):
        with temporary_project() as external:
            outside = Path(external)
            (outside / "exclude").write_bytes(b"Keep external data\n")
            (self.root / ".git/info/exclude").unlink()
            (self.root / ".git/info").rmdir()
            directory_link(self.root / ".git/info", outside)
            with self.assertRaises(ConfigError):
                init_project(self.root)
            self.assertEqual((outside / "exclude").read_bytes(), b"Keep external data\n")
            self.assertFalse((self.root / ".harness").exists())
            self.assertFalse((self.root / "AGENTS.md").exists())

    def test_internal_directory_link_is_also_rejected(self):
        (self.root / "other").mkdir()
        directory_link(self.root / ".harness", self.root / "other")
        with self.assertRaises(ConfigError):
            init_project(self.root)
        self.assertEqual(list((self.root / "other").iterdir()), [])

    def test_exclude_write_failure_creates_no_controls(self):
        exclude = (self.root / ".git/info/exclude").read_bytes()
        with patch("harness.installer.atomic_write", side_effect=PermissionError("Denied exclude")):
            with self.assertRaisesRegex(PermissionError, "Denied exclude"):
                init_project(self.root)
        self.assertFalse((self.root / ".harness").exists())
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertEqual((self.root / ".git/info/exclude").read_bytes(), exclude)

    def test_readonly_exclude_is_rejected_in_preflight(self):
        import stat

        exclude = self.root / ".git/info/exclude"
        original_mode = exclude.stat().st_mode
        exclude.chmod(stat.S_IREAD)
        self.addCleanup(exclude.chmod, original_mode)
        with self.assertRaises(ConfigError):
            init_project(self.root)
        self.assertFalse((self.root / ".harness").exists())
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_partial_control_write_rolls_back_and_keeps_protection(self):
        open_file = Path.open

        def fail_config(path, *args, **kwargs):
            if path.name == "harness.json" and args == ("xb",):
                raise OSError("Simulated control write failure")
            return open_file(path, *args, **kwargs)

        with patch.object(Path, "open", fail_config):
            with self.assertRaisesRegex(OSError, "Simulated control write failure"):
                init_project(self.root)
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertFalse((self.root / ".harness").exists())
        self.assert_protected()
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), b"")
        init_project(self.root)
        self.assert_protected()

    def test_failure_during_write_removes_partial_content_and_preserves_existing_files(self):
        agents = self.root / "AGENTS.md"
        agents.write_bytes(b"Preserve local instructions\r\n")
        open_file = Path.open

        class PartialWriter:
            def __enter__(self):
                self.stream = open_file(self.root / ".harness/pendencias.md", "xb")
                return self

            def write(self, data):
                self.stream.write(data[:10])
                raise OSError("Failure after partial content")

            def __exit__(self, *args):
                self.stream.close()

        writer = PartialWriter()
        writer.root = self.root

        def fail_pending(path, *args, **kwargs):
            if path.name == "pendencias.md" and args == ("xb",):
                return writer
            return open_file(path, *args, **kwargs)

        with patch.object(Path, "open", fail_pending):
            with self.assertRaisesRegex(OSError, "Failure after partial content"):
                init_project(self.root)
        self.assertEqual(agents.read_bytes(), b"Preserve local instructions\r\n")
        self.assertFalse((self.root / ".harness").exists())
        self.assert_protected()
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), b"")

    def test_controls_are_ignored_before_the_first_directory_is_created(self):
        mkdir = Path.mkdir

        def check_before_mkdir(path, *args, **kwargs):
            if path == self.root / ".harness":
                self.assertFalse(path.exists())
                self.assert_protected()
            return mkdir(path, *args, **kwargs)

        with patch.object(Path, "mkdir", check_before_mkdir):
            init_project(self.root)

    def test_readonly_control_directory_aborts_before_changing_exclude(self):
        exclude = (self.root / ".git/info/exclude").read_bytes()
        with patch("harness.project_storage.os.access", return_value=False):
            with self.assertRaisesRegex(ConfigError, "cannot write"):
                init_project(self.root)
        self.assertFalse((self.root / ".harness").exists())
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertEqual((self.root / ".git/info/exclude").read_bytes(), exclude)

    def test_deleted_tracked_instructions_are_not_recreated(self):
        agents = self.root / "AGENTS.md"
        agents.write_bytes(b"Tracked instructions\n")
        self.git("add", "--", "AGENTS.md")
        agents.unlink()
        index = self.git("ls-files", "--stage")
        status = self.git("status", "--porcelain", "--untracked-files=all")
        init_project(self.root)
        self.assertFalse(agents.exists())
        self.assertTrue((self.root / ".harness/AGENTS.md").is_file())
        self.assertEqual(self.git("ls-files", "--stage"), index)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), status)
