import contextlib
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
        from harness.project_update import update_project
        agents = self.root / "AGENTS.md"
        current = PROJECT_FILES["AGENTS.md"]
        old = current[:current.index("## Memória e documentação seletivas")] + current[current.index("## Restrições permanentes do projeto"):]
        old = old.replace(".harness/planos/", "planos/").replace("`.harness/harness.json`", "`harness.json`")
        old += "\n- Nunca alterar o limite de 300 entregas.\n"
        agents.write_bytes(old.encode("utf-8"))
        summary = update_project(self.root)
        updated = agents.read_text(encoding="utf-8")
        self.assertIn("## Memória e documentação seletivas", updated)
        self.assertIn("Nunca alterar o limite de 300 entregas.", updated)
        self.assertIn("`.harness/harness.json`", updated)
        self.assertNotIn("Se `harness.json`", updated)
        self.assertEqual((Path(summary["backup"]) / "AGENTS.md").read_bytes(), old.encode("utf-8"))
        again = update_project(self.root)
        self.assertEqual(agents.read_text(encoding="utf-8"), updated)
        self.assertEqual(again["updated"], [])

    def test_preserves_checks_task_memory_and_custom_agents(self):
        from harness.project_update import update_project
        config_path = self.root / ".harness/harness.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["checks"] = {"custom": {"state": "unconfigured", "reason": "Preservar"}}
        config_path.write_text(json.dumps(config), encoding="utf-8")
        (self.root / "AGENTS.md").write_text("# Meu projeto\n\nNão migrar Routes API.\n", encoding="utf-8")
        task = self.root / ".harness/planos/instrucoes.md"
        task.write_text("# Tarefa em andamento\n\nNão alterar src/mobile.\n", encoding="utf-8")
        memory = self.root / ".harness/memoria/decisoes.md"
        memory.write_text("# Decisões\n\nD1: manter banco existente.\n", encoding="utf-8")
        update_project(self.root)
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

    def test_cli_updates_project_without_git_or_pip(self):
        from harness.updater import main
        with patch("harness.updater.update_app") as app, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--project", str(self.root)]), 0)
        app.assert_not_called()

    def test_preserves_edits_inside_managed_block_on_next_update(self):
        from harness.project_update import update_project
        update_project(self.root)
        path = self.root / "AGENTS.md"
        current = path.read_text(encoding="utf-8")
        current = current.replace("## Verificação", "- Regra local: não alterar APIs.\n\n## Verificação")
        path.write_text(current, encoding="utf-8")
        update_project(self.root)
        result = path.read_text(encoding="utf-8")
        self.assertEqual(result.count("Regra local: não alterar APIs."), 1)
        self.assertGreater(result.index("Regra local: não alterar APIs."), result.index("<!-- harness:managed:end -->"))
        update_project(self.root)
        self.assertEqual(path.read_text(encoding="utf-8"), result)

    def test_legacy_custom_constraints_remain_discoverable_after_migration(self):
        from harness.project_update import update_project
        for directory in ("planos", "memoria"):
            (self.root / directory).mkdir()
        constraints = self.root / "planos/IMPLEMENTATION_CONSTRAINTS.md"
        constraints.write_text("Preservar limite de 300 entregas.", encoding="utf-8")
        memory = self.root / "memoria/operacao.md"
        memory.write_text("Regra operacional confirmada.", encoding="utf-8")
        update_project(self.root)
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("consulte `planos/IMPLEMENTATION_CONSTRAINTS.md`", agents)
        self.assertIn("mesmo quando os diretórios em `.harness/` já existirem", agents)
        self.assertIn("arquivos personalizados do legado", agents)
        self.assertEqual(constraints.read_text(encoding="utf-8"), "Preservar limite de 300 entregas.")
        self.assertEqual(memory.read_text(encoding="utf-8"), "Regra operacional confirmada.")


if __name__ == "__main__":
    unittest.main()
