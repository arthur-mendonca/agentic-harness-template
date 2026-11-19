import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from harness import tasks
from harness.config import load_config
from harness.installer import init_project
from harness.project_storage import project_lock
from harness.runner import main, run
from harness.sdd_policy import RISKS, choose_mode, parse_risks
from tests.helpers import directory_link, temporary_project


class TaskTests(unittest.TestCase):
    def setUp(self):
        directory = temporary_project()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        init_project(self.root)

    def invoke(self, *args, exit_code=0):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["sdd", "--project", str(self.root), *args])
        self.assertEqual(code, exit_code, stdout.getvalue() + stderr.getvalue())
        return json.loads(stdout.getvalue()) if code == 0 else stderr.getvalue()

    def new(self, title="Ajustar rótulo", *args):
        return self.invoke("new", "--title", title, *args)

    def documents(self, task):
        return {path.name for path in (self.root / task["path"]).iterdir()}

    def test_auto_creates_lite_for_an_assessed_small_change(self):
        task = self.new("Ajustar rótulo", "--assessed-low")
        self.assertEqual(task["mode"], "lite")
        self.assertTrue(task["mode_reason"])
        self.assertEqual(self.documents(task), {"meta.json", "tarefa.md"})
        text = (self.root / task["path"] / "tarefa.md").read_text(encoding="utf-8")
        for heading in ("Objetivo", "Critérios de aceite", "Passos", "Verificação"):
            self.assertIn("## " + heading, text)

    def test_auto_selects_full_for_material_risk_or_incomplete_assessment(self):
        for title, flags in (
            ("Rever integração", ("--assessed-low", "--risk", "service_cost=material")),
            ("Alteração sem contexto", ()),
        ):
            with self.subTest(title=title):
                task = self.new(title, *flags)
                self.assertEqual(task["mode"], "full")
                self.assertEqual(self.documents(task), {"meta.json", "spec.md", "plan.md", "tasks.md"})

    def test_resuming_a_trivial_task_with_explicit_auto_keeps_the_lite_layout(self):
        task = self.new("Retomar ajuste de rótulo", "--mode", "lite")
        resumed = self.invoke("mode", task["id"], "auto", "--assessed-low")
        self.assertEqual(resumed["id"], task["id"])
        self.assertEqual(resumed["mode"], "lite")
        self.assertEqual(self.documents(resumed), {"meta.json", "tarefa.md"})
        self.assertEqual(len(self.invoke("list")["tasks"]), 1)

    def test_off_has_no_files_and_an_explicit_mode_overrides_config(self):
        path = self.root / ".harness/harness.json"
        config = load_config(self.root)
        config["sdd"] = {"mode": "off"}
        path.write_text(json.dumps(config), encoding="utf-8")
        before = set(self.root.rglob("*"))
        self.assertEqual(self.new()["mode"], "off")
        self.assertEqual(self.new("Pedido direto", "--mode", "off")["mode"], "off")
        self.assertEqual(set(self.root.rglob("*")), before)
        self.assertEqual(self.new("Pedido gerenciado", "--mode", "lite", "--risk", "data=material")["mode"], "lite")
        self.assertEqual(self.new("Seleção automática", "--mode", "auto", "--assessed-low")["mode"], "lite")

    def test_explicit_off_needs_no_configuration(self):
        with temporary_project() as directory, contextlib.redirect_stdout(io.StringIO()) as output:
            root = Path(directory)
            self.assertEqual(main(["sdd", "new", "--project", str(root), "--mode", "off", "--title", "Ajuste"]), 0)
            self.assertEqual(json.loads(output.getvalue())["mode"], "off")
            self.assertEqual(list(root.iterdir()), [])

    def test_number_is_never_reused_even_after_all_tasks_are_removed(self):
        first = self.new("Primeira", "--mode", "lite")
        folder = self.root / first["path"]
        for path in folder.iterdir():
            path.unlink()
        folder.rmdir()
        folder.parent.rmdir()

        second = self.new("Segunda", "--mode", "lite")
        self.assertEqual(second["number"], first["number"] + 1)
        self.assertNotEqual(second["id"], first["id"])

    def test_promotion_moves_lite_sections_and_preserves_status_and_identity(self):
        task = self.new("Ajustar validação", "--mode", "lite")
        folder = self.root / task["path"]
        lite = folder / "tarefa.md"
        original = lite.read_text(encoding="utf-8").replace(
            "## Objetivo\n", "## Objetivo\n\nPreserve a fila de expedição.\n"
        ).replace("## Passos\n", "## Passos\n\n- Investigue a fila.\n")
        lite.write_text(original, encoding="utf-8")
        self.invoke("set-status", task["id"], "blocked")
        updated = self.invoke("mode", "001", "full")
        self.assertEqual(updated["id"], task["id"])
        self.assertEqual(updated["path"], task["path"])
        self.assertEqual(updated["status"], "blocked")
        self.assertEqual(updated["verification"], "impeded")
        self.assertEqual(self.documents(updated), {"meta.json", "spec.md", "plan.md", "tasks.md"})
        self.assertIn("Preserve a fila", (folder / "spec.md").read_text(encoding="utf-8"))
        self.assertIn("- Investigue a fila.", (folder / "tasks.md").read_text(encoding="utf-8"))
        self.assertEqual((self.root / updated["backup"] / "tarefa.md").read_text(encoding="utf-8"), original)
        self.assertEqual(self.invoke("resume", task["id"])["path"], task["path"])
        self.assertEqual(len(self.invoke("list")["tasks"]), 1)

    def test_verified_requires_a_selected_passing_check(self):
        path = self.root / ".harness/harness.json"
        config = load_config(self.root)
        config["checks"] = {"smoke": {"state": "configured", "command": [sys.executable, "-c", "print('ok')"],
                                     "cwd": ".", "timeout": 10}}
        path.write_text(json.dumps(config), encoding="utf-8")
        task = self.new("Ajuste verificado", "--mode", "lite")
        self.invoke("set-status", task["id"], "verified", exit_code=2)
        report, code, evidence = run(self.root, ["smoke"])
        self.assertEqual(code, 0, report)
        reference = evidence.relative_to(self.root).as_posix()
        self.assertEqual(self.invoke("set-status", task["id"], "verified", "--evidence", reference)["verification"], "verified")
        done = self.invoke("set-status", task["id"], "completed")
        self.assertEqual(done["status"], "completed")
        self.assertEqual(done["evidence"], [reference])

    def test_non_applicable_check_is_never_verified_even_when_runner_exits_zero(self):
        path = self.root / ".harness/harness.json"
        config = load_config(self.root)
        config["checks"] = {"optional": {"state": "not_applicable", "reason": "Sem interface"}}
        path.write_text(json.dumps(config), encoding="utf-8")
        task = self.new("Ajuste", "--mode", "lite")
        _, code, evidence = run(self.root, ["optional"])
        self.assertEqual(code, 0)
        message = self.invoke("set-status", task["id"], "verified", "--evidence",
                              evidence.relative_to(self.root).as_posix(), exit_code=2)
        self.assertIn("Selected checks must have passed", message)
        self.assertEqual(self.invoke("status", task["id"])["verification"], "unverified")

    def test_manual_verification_is_recorded_without_requiring_automated_checks(self):
        from tests.test_specs import PLAN, SPEC, TASKS

        task = self.new("Revisar saída visual", "--mode", "lite")
        proof = self.root / task["path"] / "tarefa.md"
        with proof.open("a", encoding="utf-8") as stream:
            stream.write("\nConferi a saída nas duas resoluções previstas.\n")
        reference = proof.relative_to(self.root).as_posix()
        checked = self.invoke("set-status", task["id"], "verified", "--manual-evidence", reference)
        self.assertEqual(checked["manual_evidence"], [reference])
        self.assertEqual(checked["evidence"], [])
        promoted = self.invoke("mode", task["id"], "full")
        self.assertEqual(promoted["manual_evidence"], [f"{promoted['backup']}/tarefa.md"])
        for name, content in (("spec.md", SPEC), ("plan.md", PLAN), ("tasks.md", TASKS)):
            (self.root / promoted["path"] / name).write_bytes(content.encode("utf-8"))
        self.assertEqual(self.invoke("set-status", task["id"], "completed")["status"], "completed")

    def test_a_passing_check_can_coexist_with_non_applicable_checks(self):
        path = self.root / ".harness/harness.json"
        config = load_config(self.root)
        config["checks"] = {
            "smoke": {"state": "configured", "command": [sys.executable, "-c", "print('ok')"], "cwd": ".", "timeout": 10},
            "optional": {"state": "not_applicable", "reason": "Sem interface"},
        }
        path.write_text(json.dumps(config), encoding="utf-8")
        task = self.new("Ajuste", "--mode", "lite")
        _, code, evidence = run(self.root, ["smoke", "optional"])
        self.assertEqual(code, 0)
        reference = evidence.relative_to(self.root).as_posix()
        self.assertEqual(self.invoke("set-status", task["id"], "verified", "--evidence", reference)["status"], "verified")

    def test_off_suspends_existing_task_and_lite_links_the_full_backup(self):
        task = self.new("Pausar e retomar", "--mode", "full")
        folder = self.root / task["path"]
        specific = "# Preserve as rotas por região.\n"
        (folder / "spec.md").write_text(specific, encoding="utf-8")
        off = self.invoke("mode", task["id"], "off")
        self.assertEqual(off["mode"], "off")
        self.assertEqual(self.documents(off), {"meta.json", "spec.md", "plan.md", "tasks.md"})
        self.assertEqual(self.invoke("resume", task["id"])["mode"], "off")
        self.invoke("mode", task["id"], "full")
        self.assertEqual((folder / "spec.md").read_text(encoding="utf-8"), specific)
        lite = self.invoke("mode", task["id"], "lite")
        self.assertEqual(self.documents(lite), {"meta.json", "tarefa.md"})
        link = f"../../backups/tasks/{Path(lite['backup']).name}/spec.md"
        self.assertIn(link, (folder / "tarefa.md").read_text(encoding="utf-8"))
        self.assertEqual((folder / link).resolve().read_text(encoding="utf-8"), specific)
        with (folder / "tarefa.md").open("a", encoding="utf-8") as stream:
            stream.write("\n- Rever as entradas anotadas no modo lite.\n")
        resumed = self.invoke("mode", task["id"], "full")
        self.assertEqual(self.documents(resumed), {"meta.json", "spec.md", "plan.md", "tasks.md"})
        self.assertIn(specific, (folder / "spec.md").read_text(encoding="utf-8"))
        self.assertIn("Rever as entradas", (folder / "tasks.md").read_text(encoding="utf-8"))

    def test_interrupted_promotion_recovers_only_the_affected_task(self):
        class ProcessStopped(BaseException):
            pass

        task = self.new("Alteração interrompida", "--mode", "lite")
        folder = self.root / task["path"]
        original = (folder / "tarefa.md").read_bytes()
        original_meta = (folder / "meta.json").read_bytes()
        atomic = tasks.atomic_write

        def stop_before_commit(path, data, **kwargs):
            if path == folder / "meta.json":
                self.assertFalse((folder / "tarefa.md").exists())
                raise ProcessStopped()
            atomic(path, data, **kwargs)

        with patch.object(tasks, "atomic_write", side_effect=stop_before_commit):
            with self.assertRaises(ProcessStopped):
                self.invoke("mode", task["id"], "full")
        self.assertTrue(self.invoke("list")["tasks"][0]["transition_pending"])
        self.assertIn("transition is pending", self.invoke("status", task["id"], exit_code=2))
        other = self.new("Tarefa independente", "--mode", "lite")
        self.assertNotEqual(other["id"], task["id"])
        self.assertEqual(self.invoke("resume", task["id"])["mode"], "lite")
        self.assertEqual(self.documents(task), {"meta.json", "tarefa.md"})
        self.assertEqual((folder / "tarefa.md").read_bytes(), original)
        self.assertEqual((folder / "meta.json").read_bytes(), original_meta)

    def test_failed_creation_does_not_publish_partial_task(self):
        atomic = tasks.atomic_write

        def fail_meta(path, data, **kwargs):
            if path.name == "meta.json":
                raise OSError("Simulated failure")
            atomic(path, data, **kwargs)

        with patch.object(tasks, "atomic_write", side_effect=fail_meta):
            self.invoke("new", "--title", "Tentativa interrompida", "--mode", "lite", exit_code=2)
        self.assertEqual(self.invoke("list")["tasks"], [])
        self.assertEqual(list((self.root / ".harness/tarefas").iterdir()), [])
        self.assertEqual(self.new("Tentativa bem-sucedida", "--mode", "lite")["number"], 1)

    def test_recovery_refuses_to_clear_journal_for_a_committed_but_incomplete_layout(self):
        task = self.new("Alteração com interrupção", "--mode", "lite")
        folder = self.root / task["path"]
        journal = folder / ".transition.json"
        unlink = Path.unlink

        def fail_cleanup(path, *args, **kwargs):
            if path == journal:
                raise OSError("Simulated cleanup failure")
            return unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", fail_cleanup):
            self.invoke("mode", task["id"], "full", exit_code=2)
        spec = folder / "spec.md"
        data = spec.read_bytes()
        spec.unlink()
        message = self.invoke("resume", task["id"], exit_code=2)
        self.assertIn("committed mode transition", message)
        self.assertTrue(journal.is_file())
        spec.write_bytes(data)
        self.assertEqual(self.invoke("resume", task["id"])["mode"], "full")
        self.assertFalse(journal.exists())

    def test_invalid_journal_and_metadata_are_confined_to_their_task(self):
        damaged = self.new("Tarefa danificada", "--mode", "lite")
        intact = self.new("Tarefa íntegra", "--mode", "lite")
        folder = self.root / damaged["path"]
        (folder / ".transition.json").write_text("null", encoding="utf-8")
        self.assertIn("Invalid pending task transition", self.invoke("resume", damaged["id"], exit_code=2))
        (folder / "meta.json").write_text("{", encoding="utf-8")
        self.assertEqual(self.invoke("resume", intact["id"])["id"], intact["id"])
        self.assertEqual(self.invoke("set-status", intact["id"], "blocked")["status"], "blocked")
        listing = self.invoke("list")
        self.assertEqual([task["id"] for task in listing["tasks"]], [intact["id"]])
        self.assertEqual(listing["unavailable"], [damaged["path"]])
        self.assertIn("Cannot read", self.invoke("status", "001", exit_code=2))
        (folder / "meta.json").unlink()
        self.assertEqual(self.invoke("list")["unavailable"], [damaged["path"]])

    def test_managed_creation_waits_for_legacy_controls_but_off_is_available(self):
        legacy = self.root / "planos"
        legacy.mkdir()
        (legacy / "instrucoes.md").write_text("Instrução antiga.", encoding="utf-8")
        error = self.invoke("new", "--title", "Verificar legado", "--mode", "lite", exit_code=2)
        self.assertIn("Prepare legacy project controls", error)
        self.assertEqual(self.new("Proceder sem documentação", "--mode", "off")["mode"], "off")
        self.assertFalse((self.root / ".harness/tarefas").exists())

    def test_completed_migration_state_does_not_enable_a_restored_legacy_configuration(self):
        self.invoke("new", "--title", "Original", "--mode", "lite")
        from harness.project_update import update_project

        update_project(self.root)
        config = load_config(self.root)
        config.pop("sdd")
        config["schema_version"] = 1
        (self.root / ".harness/harness.json").unlink()
        (self.root / "harness.json").write_text(json.dumps(config), encoding="utf-8")
        error = self.invoke("new", "--title", "Legado restaurado", "--mode", "lite", exit_code=2)
        self.assertIn("Prepare legacy project controls", error)
        self.assertEqual(len(self.invoke("list")["tasks"]), 1)

    def test_unsafe_transition_does_not_hide_other_tasks_from_listing(self):
        first = self.new("Primeira tarefa", "--mode", "lite")
        second = self.new("Segunda tarefa", "--mode", "lite")
        with temporary_project() as directory:
            journal = self.root / first["path"] / ".transition.json"
            directory_link(journal, Path(directory))
            entries = self.invoke("list")["tasks"]
            self.assertIn("transition_error", entries[0])
            self.assertEqual(entries[1]["id"], second["id"])

    def test_concurrent_project_writer_cannot_reserve_another_task_number(self):
        with project_lock(self.root):
            error = self.invoke("new", "--title", "Operação concorrente", "--mode", "full", exit_code=2)
        self.assertIn("Another operation is writing this project", error)
        self.assertEqual(self.new("Primeira tarefa", "--mode", "full")["number"], 1)

    def test_title_and_lookup_cannot_traverse_task_directory(self):
        task = self.new(r"../../Rótulo \ relatório", "--mode", "lite")
        self.assertEqual(task["path"], ".harness/tarefas/001-rotulo-relatorio")
        self.invoke("status", "../001-rotulo-relatorio", exit_code=2)
        self.assertEqual(self.invoke("status", "001")["id"], task["id"])

    def test_task_root_junction_is_refused_without_writing_outside(self):
        with temporary_project() as directory:
            outside = Path(directory)
            directory_link(self.root / ".harness/tarefas", outside)
            self.invoke("new", "--title", "Caminho inseguro", "--mode", "lite", exit_code=2)
            self.assertEqual(list(outside.iterdir()), [])

    def test_tracked_metadata_is_readable_but_not_rewritten(self):
        def git(*args):
            command = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True)
            self.assertEqual(command.returncode, 0, command.stderr)

        git("init", "-q")
        task = self.new("Tarefa rastreada", "--mode", "lite")
        path = f"{task['path']}/meta.json"
        original = (self.root / path).read_bytes()
        git("add", "-f", "--", path)
        self.assertEqual(self.invoke("status", task["id"])["status"], "open")
        self.assertIn("tracked file", self.invoke("set-status", task["id"], "blocked", exit_code=2))
        self.assertEqual((self.root / path).read_bytes(), original)
        self.assertEqual(self.new("Tarefa separada", "--mode", "lite")["number"], 2)

    def test_rollback_never_removes_a_document_that_became_tracked(self):
        def git(*args):
            command = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True)
            self.assertEqual(command.returncode, 0, command.stderr)

        git("init", "-q")
        task = self.new("Mudança concorrente no Git", "--mode", "lite")
        folder = self.root / task["path"]
        atomic = tasks.atomic_write

        def stage_new_file(path, data, **kwargs):
            atomic(path, data, **kwargs)
            if path == folder / "spec.md":
                git("add", "-f", "--", f"{task['path']}/spec.md")

        with patch.object(tasks, "atomic_write", side_effect=stage_new_file):
            error = self.invoke("mode", task["id"], "full", exit_code=2)
        self.assertIn("tracked file", error)
        self.assertTrue((folder / "spec.md").is_file())
        self.assertTrue((folder / "tarefa.md").is_file())
        self.assertTrue((folder / ".transition.json").is_file())


class SDDPolicyTests(unittest.TestCase):
    def test_all_risk_factors_can_require_full_even_if_other_risks_are_low(self):
        for factor in RISKS:
            with self.subTest(factor=factor):
                self.assertEqual(choose_mode("auto", risks={factor: "material"}, assessed_low=True)[0], "full")
                self.assertEqual(choose_mode("auto", risks={factor: "unknown"}, assessed_low=True)[0], "full")

    def test_duplicate_and_unknown_risk_flags_are_rejected(self):
        for flags in (["missing=low"], ["data=somewhat"], ["data=low", "data=material"]):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                parse_risks(flags)
