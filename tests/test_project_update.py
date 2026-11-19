import contextlib
from hashlib import sha256
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from harness.installer import init_project
from harness.project import PROJECT_FILES
from tests.helpers import temporary_project


class ProjectUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_project()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        init_project(self.root)

    def test_updates_old_agents_and_preserves_local_rules_with_exact_backup(self):
        from harness.project_update import END, update_project
        agents = self.root / "AGENTS.md"
        example = PROJECT_FILES["AGENTS.md"].splitlines()[3]
        old = (
            "# Instruções permanentes para agentes\r\n\r\n"
            "## Regras de roteirização\r\n\r\n"
            "- Nunca alterar o limite de 300 entregas.\r\n"
            "  - Exceções exigem autorização da expedição.\r\n\r\n"
            "## Texto usado nos testes de aceitação\r\n\r\n"
            f"```markdown\r\n{example}\r\n```\r\n"
        )
        original = old.encode("utf-8-sig")
        agents.write_bytes(original)
        summary = update_project(self.root)
        updated = agents.read_bytes()
        self.assertIn(PROJECT_FILES["AGENTS.md"].rstrip().encode("utf-8"), updated)
        self.assertEqual(updated.split(END.encode("utf-8"))[1], b"\n\n" + old.encode("utf-8"))
        self.assertEqual((Path(summary["backup"]) / "AGENTS.md").read_bytes(), original)
        again = update_project(self.root)
        self.assertEqual(agents.read_bytes(), updated)
        self.assertEqual(again["updated"], [])
        self.assertIsNone(again["backup"])

    def test_preserves_checks_task_memory_and_custom_agents(self):
        from harness.project_update import update_project
        config_path = self.root / ".harness/harness.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["checks"] = {"custom": {"state": "unconfigured", "reason": "Preservar"}}
        config_path.write_text(json.dumps(config), encoding="utf-8")
        (self.root / "AGENTS.md").write_text("# Meu projeto\n\nNão migrar Routes API.\n", encoding="utf-8")
        task = self.root / ".harness/planos/instrucoes.md"
        task.parent.mkdir()
        task.write_text("# Tarefa em andamento\n\nNão alterar src/mobile.\n", encoding="utf-8")
        memory = self.root / ".harness/memoria/decisoes.md"
        memory.write_text("# Decisões\n\nD1: manter banco existente.\n", encoding="utf-8")
        preview = update_project(self.root, dry_run=True)
        review = {"destinations": preview["destinations"], "sources": {task.relative_to(self.root).as_posix(): {
            "sha256": sha256(task.read_bytes()).hexdigest(),
            "findings": [{"category": "task", "text": "Não alterar src/mobile.", "line": 3}],
        }}}
        self.assertEqual(update_project(self.root, review=review)["status"], "complete")
        self.assertEqual(json.loads(config_path.read_text(encoding="utf-8"))["checks"], config["checks"])
        self.assertIn("Não migrar Routes API.", (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertIn("Não alterar src/mobile.", task.read_text(encoding="utf-8"))
        self.assertIn("D1: manter banco existente.", memory.read_text(encoding="utf-8"))

    def test_malformed_managed_block_aborts_before_other_writes(self):
        from harness.project_update import update_project
        from harness.config import ConfigError
        before = (self.root / "AGENTS.md").read_bytes()
        path = self.root / ".harness/memoria/decisoes.md"
        path.write_text("<!-- harness:managed:start -->\nbroken", encoding="utf-8")
        with self.assertRaises(ConfigError):
            update_project(self.root)
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), before)
        self.assertFalse((self.root / ".harness/backups").exists())

    def test_cli_updates_project_without_reinstalling_the_app(self):
        from harness.updater import main
        with patch("harness.updater.update_app") as app, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--project", str(self.root)]), 0)
        app.assert_not_called()

    def test_preserves_edits_inside_managed_block_on_next_update(self):
        from harness.project_update import update_project
        update_project(self.root)
        path = self.root / "AGENTS.md"
        current = path.read_text(encoding="utf-8")
        current = current.replace("## Regras permanentes do projeto", "- Regra local: não alterar APIs.\n\n## Regras permanentes do projeto")
        path.write_text(current, encoding="utf-8")
        update_project(self.root)
        result = path.read_text(encoding="utf-8")
        self.assertEqual(result.count("Regra local: não alterar APIs."), 1)
        self.assertGreater(result.index("Regra local: não alterar APIs."), result.index("<!-- harness:managed:end -->"))
        update_project(self.root)
        self.assertEqual(path.read_text(encoding="utf-8"), result)

    def test_replaces_a_managed_block_matching_its_snapshot(self):
        from harness.project_update import END, START, STATE, update_project
        path = self.root / "AGENTS.md"
        previous = "# Instruções anteriores\n\n- Execute a verificação antiga.\n"
        state = self.root / STATE
        state.write_text(json.dumps({"AGENTS.md": previous}), encoding="utf-8")
        custom = "\n## Regras locais\n\n- Preserve a ordem de expedição.\n"
        original = f" {START}\n<!-- harness:version 0.1.0 -->\n{previous}{END}\n{custom}".replace("\n", "\r")
        path.write_bytes(original.encode("utf-8"))

        summary = update_project(self.root)

        updated = path.read_text(encoding="utf-8")
        self.assertIn(PROJECT_FILES["AGENTS.md"], updated)
        self.assertNotIn(previous, updated)
        self.assertTrue(updated.endswith(custom))
        self.assertEqual((Path(summary["backup"]) / "AGENTS.md").read_bytes(), original.encode("utf-8"))
        self.assertEqual(update_project(self.root)["updated"], [])

    def test_preserves_a_template_heading_used_as_literal_markdown(self):
        from harness.project_update import END, update_project
        update_project(self.root)
        path = self.root / "AGENTS.md"
        heading = "## Regras permanentes do projeto"
        example = f"```markdown\n\n{heading}\n\n```"
        edited = path.read_text(encoding="utf-8").replace(heading, example)
        path.write_text(edited, encoding="utf-8")

        update_project(self.root)

        updated = path.read_text(encoding="utf-8")
        self.assertIn(example, updated.split(END)[1])
        self.assertEqual(update_project(self.root)["updated"], [])

    def test_ignores_ownership_markers_inside_a_markdown_example(self):
        from harness.project_update import END, START, update_project
        path = self.root / "AGENTS.md"
        original = f"## Exemplo\n\n````markdown\n{START}\n```\n{END}\n````\n"
        path.write_bytes(original.encode("utf-8"))

        update_project(self.root)

        updated = path.read_bytes()
        self.assertTrue(updated.startswith(START.encode("utf-8")))
        self.assertTrue(updated.endswith(original.encode("utf-8")))
        self.assertEqual(update_project(self.root)["updated"], [])

    def test_legacy_files_and_unrecorded_managed_rules_are_preserved(self):
        from harness.project_update import END, START, update_project
        agents_path = self.root / "AGENTS.md"
        rules = (
            "## Restrição do projeto\n\n"
            "- Consulte `planos/instrucoes.md` para as instruções e o planejamento da tarefa. "
            "Leia também `planos/IMPLEMENTATION_CONSTRAINTS.md`, quando existir.\n"
            "  Essa regra cobre o limite de entregas."
        )
        agents_path.write_text(f"{START}\n<!-- harness:version 0.1.0 -->\n{rules}\n{END}\n", encoding="utf-8")
        for directory in ("planos", "memoria"):
            (self.root / directory).mkdir()
        constraints = self.root / "planos/IMPLEMENTATION_CONSTRAINTS.md"
        constraints.write_text("Preservar limite de 300 entregas.", encoding="utf-8")
        memory = self.root / "memoria/operacao.md"
        memory.write_text("Regra operacional confirmada.", encoding="utf-8")
        data = agents_path.read_bytes()
        initial = update_project(self.root, dry_run=True)
        review = {"destinations": initial["destinations"],
                  "sources": {name: {"sha256": initial["inventory"][name], "findings": []}
                              for name in initial["review_required"]}}
        rule = "  Preserve a regra do limite de entregas."
        review["sources"]["AGENTS.md"]["instructions"] = "## Restrição do projeto\n\n" + rule + "\n"
        review["sources"]["planos/IMPLEMENTATION_CONSTRAINTS.md"]["findings"] = [
            {"category": "rule", "text": "Preservar limite de 300 entregas.", "line": 1},
        ]
        review["sources"]["memoria/operacao.md"]["findings"] = [
            {"category": "rule", "text": "Regra operacional confirmada.", "line": 1},
        ]
        summary = update_project(self.root, review=review)
        agents = agents_path.read_text(encoding="utf-8")
        self.assertIn(PROJECT_FILES["AGENTS.md"], agents.split(END)[0])
        self.assertIn(rule, agents.split(END)[1])
        self.assertNotIn("planos/instrucoes.md", agents)
        self.assertEqual((Path(summary["backup"]) / "AGENTS.md").read_bytes(), data)
        self.assertEqual(constraints.read_text(encoding="utf-8"), "Preservar limite de 300 entregas.")
        self.assertEqual(memory.read_text(encoding="utf-8"), "Regra operacional confirmada.")


if __name__ == "__main__":
    unittest.main()
