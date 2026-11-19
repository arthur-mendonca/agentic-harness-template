import contextlib
from hashlib import sha256
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

from harness import migration
from harness.config import ConfigError, load_config
from harness.project_update import update_project
from harness.updater import main
from tests.helpers import directory_link, temporary_project


class MigrationTests(unittest.TestCase):
    def setUp(self):
        directory = temporary_project()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = {"schema_version": 1, "harness_version": "0.1", "project": "expedição", "checks": {
            "unit": {"state": "configured", "command": [sys.executable, "-m", "unittest"],
                     "cwd": "src", "timeout": 17.5},
            "manual": {"state": "unconfigured", "reason": "Exige credenciais"},
        }}
        (self.root / "src").mkdir()
        self.write("harness.json", json.dumps(self.config))

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def review(self, *entries):
        preview = update_project(self.root, dry_run=True)
        sources = {}
        for name, findings in entries:
            entry = {"sha256": preview["inventory"][name], "findings": findings}
            if migration._report(name):
                entry["archive"] = name in preview["archive_after_review"]
            sources[name] = entry
        return {"sources": sources, "destinations": preview["destinations"]}

    def test_previews_then_archives_reviewed_reports_and_preserves_checks(self):
        name = "planos/relatorios.md"
        report = self.write(name, "# Entregas\n- Limite de 300 entregas aprovado em REQ-8.\n- Testes passaram.\n")
        log = self.write(".harness/results/previous.log", "original evidence")
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

        preview = update_project(self.root, dry_run=True)
        self.assertEqual(preview["status"], "review_required")
        self.assertEqual(preview["review_required"], [name])
        self.assertEqual(preview["archive_after_review"], [name])
        self.assertEqual({p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}, before)
        self.assertEqual(update_project(self.root)["status"], "review_required")
        self.assertTrue(report.exists())

        result = update_project(self.root, review=self.review((name, [
            {"category": "rule", "text": "Limite de 300 entregas aprovado em REQ-8.", "line": 2},
        ])))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(load_config(self.root)["checks"], self.config["checks"])
        self.assertEqual(load_config(self.root)["schema_version"], 2)
        self.assertFalse(report.exists())
        self.assertEqual((Path(result["backup"]) / name).read_bytes(), before[Path(name)])
        self.assertEqual(log.read_text(encoding="utf-8"), "original evidence")
        memory = (self.root / ".harness/memoria/regras-negocio.md").read_text(encoding="utf-8")
        self.assertIn("Limite de 300 entregas aprovado em REQ-8.", memory)
        self.assertIn(f"{name}:2", memory)
        self.assertNotIn("Testes passaram", memory)
        state = json.loads((self.root / ".harness/migration-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["sources"][name], sha256(before[Path(name)]).hexdigest())
        again = update_project(self.root)
        self.assertEqual(again["updated"], [])
        self.assertIsNone(again["backup"])

    def test_review_is_invalidated_when_legacy_file_changes(self):
        name = "planos/relatorios.md"
        path = self.write(name, "- Log temporário.\n")
        review = self.review((name, []))
        self.write(name, "- Regra aprovada durante a revisão.\n")
        with self.assertRaisesRegex(ConfigError, "changed|hash"):
            update_project(self.root, review=review)
        self.assertTrue(path.exists())
        self.assertFalse((self.root / ".harness/migration-state.json").exists())

    def test_review_is_invalidated_when_the_memory_used_to_deduplicate_changes(self):
        name = "planos/relatorios.md"
        report = self.write(name, "Entrega anterior já registrada na memória.\n")
        memory = ".harness/memoria/decisoes.md"
        self.write(memory, "Decisão de entrega original.\n")
        review = self.review((name, []))
        self.write(memory, "Decisão removida enquanto a revisão estava aberta.\n")

        with self.assertRaisesRegex(ConfigError, "destinations changed"):
            update_project(self.root, review=review)
        self.assertTrue(report.is_file())
        self.assertFalse((self.root / ".harness/migration-state.json").exists())

    def test_only_explicitly_selected_harness_reports_are_archived(self):
        ordinary, report = "planos/cliente/relatorios.md", "relatorios.md"
        for name in (ordinary, report):
            self.write(name, "Documento que deve continuar no projeto.\n")
        review = self.review((ordinary, []), (report, []))
        self.assertNotIn("archive", review["sources"][ordinary])
        review["sources"][report]["archive"] = False
        result = update_project(self.root, review=review)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["archived"], [])
        self.assertTrue((self.root / ordinary).is_file())
        self.assertTrue((self.root / report).is_file())

    def test_reviewed_report_stays_when_untracked_after_a_preserve_preview(self):
        name = "relatorios.md"
        report = self.write(name, "Relatório rastreado durante a prévia.\n")
        self.git("init", "-q")
        self.git("add", "--", name)
        review = self.review((name, []))
        self.assertFalse(review["sources"][name]["archive"])
        self.git("rm", "--cached", "--", name)
        self.assertEqual(update_project(self.root, review=review)["status"], "complete")
        self.assertTrue(report.is_file())

    def test_report_referenced_by_a_tracked_agents_file_is_kept(self):
        name = "relatorios.md"
        report = self.write(name, "Relatório relevante.\n")
        original = "Consulte [o relatório](./relatorios.md).\n"
        agents = self.write("AGENTS.md", original)
        self.git("init", "-q")
        self.git("add", "--", "AGENTS.md")

        preview = update_project(self.root, dry_run=True)
        self.assertIn(name, preview["archive_ineligible"])
        self.assertNotIn(name, preview["archive_after_review"])
        result = update_project(self.root, review=self.review((name, [])))
        self.assertEqual(result["status"], "complete")
        self.assertIn(".harness/AGENTS.md", result["updated"])
        self.assertEqual(agents.read_text(encoding="utf-8"), original)
        self.assertTrue(report.exists())

    def test_read_only_report_allows_consolidation_without_archival(self):
        name = "relatorios.md"
        report = self.write(name, "Preservar limite de 300 entregas.\n")
        original_mode = stat.S_IMODE(report.stat().st_mode)
        report.chmod(stat.S_IREAD)
        try:
            review = self.review((name, [{"category": "rule", "text": "Preservar limite de 300 entregas.", "line": 1}]))
            self.assertFalse(review["sources"][name]["archive"])
            result = update_project(self.root, review=review)
            self.assertEqual(result["status"], "complete")
            self.assertIn(name, result["archive_ineligible"])
            self.assertTrue(report.exists())
        finally:
            report.chmod(original_mode)

    def test_old_root_report_reference_requires_review_of_the_agents_file(self):
        name = "relatorios.md"
        self.write(name, "Entrega anterior.\n")
        agents = self.write("AGENTS.md", "Leia [o relatório](./relatorios.md).\nPreserve a ordem de expedição.\n")
        review = self.review((name, []), ("AGENTS.md", []))
        self.assertEqual(set(update_project(self.root, dry_run=True)["review_required"]), {name, "AGENTS.md"})
        review["sources"]["AGENTS.md"]["instructions"] = "Preserve a ordem de expedição."
        self.assertEqual(update_project(self.root, review=review)["status"], "complete")
        text = agents.read_text(encoding="utf-8")
        self.assertIn("Preserve a ordem de expedição.", text)
        self.assertNotIn("relatorios.md", text)

    def test_known_old_memory_preamble_is_replaced_but_records_are_kept(self):
        from harness.project import PROJECT_FILES

        path = ".harness/memoria/problemas-conhecidos.md"
        previous = PROJECT_FILES[path].replace(".harness/pendencias.md", ".harness/planos/pendencias.md")
        file = self.write(path, previous + "\n- PR-7. Preserve o relato confirmado.\n")
        self.assertEqual(update_project(self.root)["status"], "complete")
        text = file.read_text(encoding="utf-8")
        self.assertIn("PR-7. Preserve o relato confirmado.", text)
        self.assertNotIn(".harness/planos/pendencias.md", text)
        self.assertEqual(text.count("# Problemas conhecidos"), 1)

        modified = previous.replace("\n\nRegistre", "\n\n- Restrição inserida no bloco.\n\nRegistre")
        self.write(path, modified)
        self.assertEqual(update_project(self.root)["status"], "complete")
        updated = file.read_text(encoding="utf-8")
        self.assertIn("Restrição inserida no bloco.", updated)
        self.assertNotIn(".harness/planos/pendencias.md", updated)

    def test_new_legacy_memory_entries_are_reviewed_without_copying_previous_entries_again(self):
        name = "memoria/decisoes.md"
        first = "- Use ordenação estável.\n"
        second = "- Confirme a ordem no início da expedição.\n"
        self.write(name, first)
        self.assertEqual(update_project(self.root)["status"], "complete")
        self.write(name, first + second)
        self.assertIn(name, update_project(self.root, dry_run=True)["review_required"])
        review = self.review((name, [{"category": "decision", "text": second.removeprefix("- ").strip(), "line": 2}]))
        self.assertEqual(update_project(self.root, review=review)["status"], "complete")
        active = (self.root / ".harness/memoria/decisoes.md").read_text(encoding="utf-8")
        self.assertEqual(active.count(first.strip()), 1)
        self.assertIn(second.strip(), active)

    def test_changes_to_legacy_memory_do_not_restore_an_entry_removed_from_the_destination(self):
        from harness.project import PROJECT_FILES

        legacy = "memoria/decisoes.md"
        destination = ".harness/memoria/decisoes.md"
        self.write(legacy, "- Regra removida em revisão.\n")
        self.assertEqual(update_project(self.root)["status"], "complete")
        self.write(destination, PROJECT_FILES[destination])
        self.write(legacy, "- Regra removida em revisão.\n- Regra nova confirmada.\n")
        review = self.review((legacy, [{"category": "decision", "text": "Regra nova confirmada.", "line": 2}]))
        self.assertEqual(update_project(self.root, review=review)["status"], "complete")
        active = (self.root / destination).read_text(encoding="utf-8")
        self.assertNotIn("Regra removida", active)
        self.assertIn("Regra nova confirmada.", active)

    def test_review_can_archive_transient_reports_without_making_memory_entries(self):
        name = ".harness/planos/relatorios.md"
        self.write(name, "- Prints de depuração.\n")
        result = update_project(self.root, review=self.review((name, [])))
        self.assertIn(name, result["archived"])
        self.assertFalse((self.root / name).exists())
        self.assertTrue((Path(result["backup"]) / name).is_file())
        self.assertTrue(all("depuração" not in p.read_text(encoding="utf-8") for p in (self.root / ".harness/memoria").glob("*.md")))

    def test_merges_distinct_checks_and_honors_later_canonical_edits(self):
        other = {"disabled": {"state": "not_applicable", "reason": "Manual verification"}}
        path = self.write(".harness/harness.json", json.dumps({**self.config, "checks": other}))
        self.assertEqual(update_project(self.root)["status"], "complete")
        self.assertEqual(load_config(self.root)["checks"], {**other, **self.config["checks"]})

        updated = load_config(self.root)
        updated["checks"].pop("unit")
        path.write_bytes(migration._json_bytes(updated))
        self.assertEqual(update_project(self.root)["updated"], [])
        self.assertEqual(load_config(self.root)["checks"], updated["checks"])

    def test_config_conflict_records_progress_and_review_can_be_retried(self):
        canonical = {**self.config, "checks": {**self.config["checks"], "unit": {
            **self.config["checks"]["unit"], "timeout": 55,
        }}}
        config = self.write(".harness/harness.json", json.dumps(canonical))
        name = "planos/relatorios.md"
        report = self.write(name, "Entrega anterior.\n")
        review = self.review((name, []))

        result = update_project(self.root, review=review)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("unit", result["blocked"][0])
        self.assertFalse(report.exists())
        self.assertEqual(load_config(self.root)["checks"], canonical["checks"])
        state_path = self.root / ".harness/migration-state.json"
        state = json.loads(state_path.read_bytes())
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(state["sources"][name], review["sources"][name]["sha256"])

        self.assertIsNone(update_project(self.root, review=review)["backup"])
        current = load_config(self.root)
        current["checks"]["unit"] = self.config["checks"]["unit"]
        config.write_bytes(migration._json_bytes(current))
        self.assertEqual(update_project(self.root, review=review)["status"], "complete")
        self.assertEqual(json.loads(state_path.read_bytes())["sources"][name], state["sources"][name])

    def test_duplicate_findings_are_consolidated_across_sources(self):
        first, second = "planos/relatorios.md", "planos/analise.md"
        for name in (first, second):
            self.write(name, "Fila de expedição usa ordenação estável.\n")
        finding = {"category": "decision", "text": "Fila de expedição usa ordenação estável.", "line": 1}
        casing = [{"category": "rule", "text": f"SKU {sku} recebe etiqueta.", "line": 1} for sku in ("ab", "Ab")]
        result = update_project(self.root, review=self.review((first, [finding, *casing]), (second, [finding])))
        self.assertEqual(result["status"], "complete")
        decision = self.root / ".harness/memoria/decisoes.md"
        self.assertEqual(decision.read_text(encoding="utf-8").count(finding["text"]), 1)
        rules = (self.root / ".harness/memoria/regras-negocio.md").read_text(encoding="utf-8")
        for rule in casing:
            self.assertIn(rule["text"], rules)

    def test_state_write_failure_restores_archived_and_replaced_files(self):
        name = "planos/relatorios.md"
        report = self.write(name, "Relatório original.\n")
        agents = self.write("AGENTS.md", "Regras do projeto.\n")
        original_report = report.read_bytes()
        original_agents = agents.read_bytes()
        review = self.review((name, []))
        atomic_write = migration._atomic_write

        def fail_state(path, data):
            if path.name == "migration-state.json":
                self.assertFalse(report.exists())
                raise OSError("Simulated failure after report archive")
            atomic_write(path, data)

        with patch.object(migration, "_atomic_write", side_effect=fail_state):
            with self.assertRaisesRegex(OSError, "Simulated failure"):
                update_project(self.root, review=review)
        self.assertEqual(report.read_bytes(), original_report)
        self.assertEqual(agents.read_bytes(), original_agents)
        self.assertEqual(load_config(self.root), self.config)
        self.assertFalse((self.root / ".harness/migration-state.json").exists())
        self.assertEqual(update_project(self.root, review=review)["status"], "complete")

    def test_missing_report_review_never_applies_even_if_other_sources_are_reviewed(self):
        first, second = "planos/relatorios.md", "planos/analise.md"
        self.write(first, "Relatório.\n")
        self.write(second, "Análise.\n")
        result = update_project(self.root, review=self.review((first, [])))
        self.assertEqual(result["review_required"], [second])
        self.assertEqual(result["status"], "review_required")
        self.assertTrue((self.root / first).is_file())
        self.assertFalse((self.root / ".harness").exists())

    def test_cli_dry_run_prints_json_and_leaves_old_configuration_active(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["--project", str(self.root), "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn(".harness/harness.json", json.loads(stdout.getvalue())["updated"])
        self.assertEqual(load_config(self.root), self.config)

    def test_cli_consumes_review_and_reports_archived_source(self):
        name = "planos/relatorios.md"
        self.write(name, "Entrega anterior.\n")
        manifest = self.write("revisao.json", json.dumps(self.review((name, []))))
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["--project", str(self.root), "--migration-review", str(manifest)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["archived"], [name])

    def test_legacy_documents_can_migrate_without_an_existing_configuration(self):
        (self.root / "harness.json").unlink()
        past = "planos/relatorios.md"
        self.write(past, "Log de execução antigo.\n")
        self.write("package.json", '{"scripts":{"test":"node tests.js"}}')

        review = self.review((past, []))
        self.assertFalse((self.root / ".harness").exists())
        self.assertEqual(update_project(self.root, review=review)["status"], "complete")
        self.assertEqual(load_config(self.root)["checks"]["test"]["command"], ["npm", "run", "test"])

    def test_legacy_directory_link_cannot_escape_the_project(self):
        with temporary_project() as external:
            directory_link(self.root / "planos", Path(external))
            with self.assertRaises(ConfigError):
                update_project(self.root)
        self.assertFalse((self.root / ".harness").exists())

    def test_tracked_controls_are_preserved_and_local_alternatives_are_ignored(self):
        agents = self.write("AGENTS.md", "# Regras específicas\nPreserve a ordem da fila.\n")
        name = "planos/relatorios.md"
        report = self.write(name, "- Log transitório.\n")
        self.git("init", "-q")
        self.git("add", "--", "AGENTS.md", "harness.json", name)
        index = self.git("ls-files", "--stage")

        result = update_project(self.root, review=self.review((name, [])))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(self.git("ls-files", "--stage"), index)
        self.assertEqual(agents.read_text(encoding="utf-8"), "# Regras específicas\nPreserve a ordem da fila.\n")
        self.assertEqual(report.read_text(encoding="utf-8"), "- Log transitório.\n")
        self.assertIn(name, result["tracked"])
        self.assertIn(".harness/AGENTS.md", result["updated"])
        self.assertFalse((self.root / ".gitignore").exists())
        self.assertIn(".harness/harness.json", self.git("check-ignore", ".harness/harness.json"))

    def test_tracked_old_schema_remains_usable_and_blocks_the_upgrade(self):
        original = self.write(".harness/harness.json", json.dumps(self.config)).read_bytes()
        self.git("init", "-q")
        self.git("add", "--", ".harness/harness.json")

        result = update_project(self.root)
        self.assertEqual(result["status"], "blocked")
        self.assertIn(".harness/harness.json", result["tracked"])
        self.assertEqual((self.root / ".harness/harness.json").read_bytes(), original)
        self.assertEqual(load_config(self.root), self.config)
        self.assertTrue((self.root / "AGENTS.md").is_file())
        self.assertIn("AGENTS.md", self.git("check-ignore", "AGENTS.md"))

    def test_git_excludes_still_hide_backup_after_a_failed_apply(self):
        self.git("init", "-q")
        atomic_write = migration._atomic_write

        def fail_config(path, data):
            if path.name == "harness.json":
                raise OSError("Simulated config write failure")
            atomic_write(path, data)

        with patch.object(migration, "_atomic_write", side_effect=fail_config):
            with self.assertRaisesRegex(OSError, "Simulated config write failure"):
                update_project(self.root)
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertEqual(load_config(self.root), self.config)
        self.assertTrue(any((self.root / ".harness/backups").glob("migration-*/harness.json")))
        self.assertIn(".harness/", self.git("check-ignore", ".harness/"))

    def test_partial_backup_is_removed_when_git_protection_has_not_been_applied(self):
        self.git("init", "-q")
        self.write("AGENTS.md", "Regra original.\n")
        self.write(".harness/memoria/decisoes.md", "Decisões originais.\n")
        open_file = Path.open
        exclude = (self.root / ".git/info/exclude").read_bytes()

        def fail_second_backup(path, *args, **kwargs):
            if args == ("xb",) and path.name == "decisoes.md":
                raise OSError("Simulated backup failure")
            return open_file(path, *args, **kwargs)

        with patch.object(Path, "open", fail_second_backup):
            with self.assertRaisesRegex(OSError, "Simulated backup failure"):
                update_project(self.root)
        self.assertFalse(list((self.root / ".harness/backups").glob("migration-*")))
        self.assertEqual((self.root / ".git/info/exclude").read_bytes(), exclude)
        self.assertEqual(load_config(self.root), self.config)

    def test_blocked_active_instructions_defer_report_archive(self):
        self.git("init", "-q")
        self.write(".gitignore", "/.harness/\n!AGENTS.md\n")
        self.git("add", "--", ".gitignore")
        agents = self.write("AGENTS.md", "Leia relatorios.md.\n")
        report = self.write("relatorios.md", "Entrega anterior.\n")
        review = self.review(("AGENTS.md", []), ("relatorios.md", []))
        review["sources"]["AGENTS.md"]["instructions"] = ""

        result = update_project(self.root, review=review)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Leia relatorios.md", agents.read_text(encoding="utf-8"))
        self.assertTrue(report.is_file())
        state = json.loads((self.root / ".harness/migration-state.json").read_bytes())
        self.assertNotIn("relatorios.md", state["sources"])

    def test_nested_project_uses_its_untracked_ignore_file_without_editing_parent_git(self):
        self.git("init", "-q")
        self.write("nested/harness.json", json.dumps({**self.config, "checks": {}}))
        root_exclude = self.root / ".git/info/exclude"
        original = root_exclude.read_bytes()
        self.write("nested/.gitignore", "# Preserve this rule\n*.tmp\n")

        result = update_project(self.root / "nested")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(root_exclude.read_bytes(), original)
        local = (self.root / "nested/.gitignore").read_text(encoding="utf-8")
        self.assertTrue(local.startswith("# Preserve this rule\n*.tmp\n"))
        self.assertIn("nested/AGENTS.md", self.git("check-ignore", "nested/AGENTS.md"))
        self.assertIn("nested/.harness/", self.git("check-ignore", "nested/.harness/"))

    def test_index_change_during_mechanical_migration_rolls_back_workspace(self):
        self.git("init", "-q")
        agents = self.write("AGENTS.md", "Instruções locais originais.\n")
        atomic_write = migration._atomic_write

        def stage_original_agents_after_config(path, data):
            atomic_write(path, data)
            if path == self.root / ".harness/harness.json":
                self.git("add", "-f", "--", "AGENTS.md")

        with patch.object(migration, "_atomic_write", side_effect=stage_original_agents_after_config):
            with self.assertRaisesRegex(ConfigError, "index changed"):
                update_project(self.root)
        self.assertEqual(agents.read_text(encoding="utf-8"), "Instruções locais originais.\n")
        self.assertFalse((self.root / ".harness/migration-state.json").exists())

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout
