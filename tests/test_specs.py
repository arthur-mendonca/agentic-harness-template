import contextlib
from hashlib import sha256
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from harness.installer import init_project
from harness.runner import main
from tests.helpers import temporary_project


SPEC = """# Ajustar o rótulo

## Objetivo
Exibir o rótulo correto.

## Escopo
Uma tela de configuração.

## Comportamento esperado
O campo mantém seu valor ao editar.

## Requisitos
- REQ-001: Exibir o rótulo com acento.

## Critérios de aceite
- AC-001 (REQ-001): A tela exibe Usuário.

## Restrições e erros
A alteração preserva o formulário existente.
"""
PLAN = """# Ajustar o rótulo

## Componentes
Tela de configuração.

## Estratégia e decisões
Atualizar o texto no recurso de idioma.

## Impactos
O texto é local. A mudança não altera chamadas externas.

## Riscos e alternativas
Conferir a largura da tela em dois tamanhos.

## Verificações planejadas
- AC-001: Abra a tela e compare o rótulo.
"""
TASKS = """# Ajustar o rótulo

## Passos
- [x] T-001 (REQ-001, AC-001): Corrigir o texto.

## Verificação
- T-001: Tela conferida nos dois tamanhos.
"""


class _Terminal(io.StringIO):
    def isatty(self):
        return True


class SpecificationTests(unittest.TestCase):
    def setUp(self):
        directory = temporary_project()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        init_project(self.root)
        task = self.invoke("new", "--title", "Ajustar o rótulo", "--mode", "full")
        self.folder = self.root / task["path"]
        self.id = task["id"]

    def invoke(self, *args, code=0, confirmation=None):
        output = io.StringIO()
        errors = _Terminal() if confirmation is not None else io.StringIO()
        stdin = _Terminal(confirmation + "\n") if confirmation is not None else io.StringIO()
        with (contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors),
              patch("harness.sdd_cli.sys.stdin", stdin)):
            result = main(["sdd", "--project", str(self.root), *args])
        self.assertEqual(result, code, output.getvalue() + errors.getvalue())
        return json.loads(output.getvalue()) if output.getvalue() else errors.getvalue()

    def write_contract(self, *, spec=SPEC, plan=PLAN, tasks=TASKS):
        for name, text in (("spec.md", spec), ("plan.md", plan), ("tasks.md", tasks)):
            (self.folder / name).write_bytes(text.encode("utf-8"))

    def test_draft_diagnostics_and_valid_trace_are_deterministic(self):
        empty = self.invoke("validate", self.id, code=1)
        self.assertFalse(empty["valid"])
        self.assertEqual(empty["spec_status"], "draft")
        self.write_contract()
        self.assertTrue(self.invoke("validate", self.id)["valid"])
        trace = self.invoke("trace", self.id)
        criterion = trace["requirements"][0]["criteria"][0]
        self.assertEqual(criterion["id"], "AC-001")
        self.assertEqual(criterion["tasks"][0]["id"], "T-001")
        self.assertTrue(criterion["planned_verifications"])
        self.assertEqual(trace, self.invoke("trace", self.id))

    def test_diagnostics_locate_duplicates_missing_coverage_and_invalid_links(self):
        spec = SPEC.replace("## Critérios", "- REQ-001: Duplicado.\n- REQ-002: Isolado.\n\n## Critérios")
        plan = PLAN.replace("AC-001:", "AC-999:").replace("Tela de configuração.", "[Arquivo](ausente.md)")
        tasks = TASKS.replace("REQ-001, AC-001", "REQ-999, AC-999")
        self.write_contract(spec=spec, plan=plan, tasks=tasks)
        result = self.invoke("validate", self.id, code=1)
        diagnostics = result["diagnostics"]
        codes = {item["code"] for item in diagnostics}
        self.assertTrue({"duplicate_id", "unknown_reference", "unverified_criterion", "unused_criterion",
                         "requirement_without_criterion", "broken_link"} <= codes, diagnostics)
        duplicate = next(item for item in diagnostics if item["code"] == "duplicate_id")
        self.assertEqual(duplicate["file"], "spec.md")
        self.assertEqual(spec.splitlines()[duplicate["line"] - 1], "- REQ-001: Duplicado.")

    def test_closure_requires_linked_and_finished_work(self):
        self.write_contract(tasks=TASKS.replace("[x]", "[ ]"))
        evidence = (self.folder / "tasks.md").relative_to(self.root).as_posix()
        self.invoke("set-status", self.id, "verified", "--manual-evidence", evidence, code=2)
        self.assertIn("T-001", self.invoke("set-status", self.id, "completed", code=2))
        self.assertEqual(self.invoke("status", self.id)["status"], "open")
        self.write_contract()
        self.invoke("review-policy", self.id, "optional", "--reason", "Explicit fixture waiver", "--decided-by", "test project")
        self.assertIn("sdd verify", self.invoke("set-status", self.id, "completed", code=2))
        assessment = self.root / ".harness/assessment.json"
        assessment.write_text(json.dumps({
            "contract": self.invoke("verify", self.id, code=1)["contract"],
            "source_snapshot": self.invoke("verify", self.id, code=1)["source_snapshot"],
            "criteria": {"AC-001": {"status": "met", "reason": "Conferi o rótulo nas duas resoluções.",
                                    "evidence": [{"file": evidence, "limitation": "Manual fixture observation"}]}},
            "review": {"status": "not_performed", "reason": "Revisor indisponível"},
        }), encoding="utf-8")
        self.invoke("verify", self.id, "--assessment", str(assessment))
        self.assertEqual(self.invoke("set-status", self.id, "completed")["status"], "completed")
        (self.folder / "tasks.md").write_bytes(TASKS.replace("AC-001", "AC-999").encode("utf-8"))
        self.assertEqual(self.invoke("status", self.id)["status"], "in_progress")
        self.assertTrue(self.invoke("status", self.id)["completion_stale"])

    def test_only_interactive_confirmation_approves_current_specification(self):
        self.write_contract()
        waiting = self.invoke("await-decision", self.id)
        self.assertEqual((waiting["spec_status"], waiting["status"]), ("awaiting_decision", "open"))
        self.assertIn("interactive", self.invoke("approve", self.id, code=2))
        self.assertIn("approval", self.invoke("set-status", self.id, "in_progress", code=2))
        self.assertIn("approval", self.invoke("mode", self.id, "lite", code=2))
        digest = sha256((self.folder / "spec.md").read_bytes()).hexdigest()
        approved = self.invoke("approve", self.id, confirmation=digest)
        self.assertEqual((approved["spec_status"], approved["status"]), ("approved", "open"))
        self.write_contract(spec=SPEC.replace("Uma tela", "Duas telas"))
        self.assertEqual(self.invoke("status", self.id)["spec_status"], "awaiting_decision")
        self.assertIn("approval", self.invoke("set-status", self.id, "in_progress", code=2))

    def test_allocated_references_do_not_change_after_editing_content(self):
        self.write_contract()
        self.assertEqual(self.invoke("allocate-id", self.id, "REQ")["id"], "REQ-002")
        self.write_contract(spec=SPEC.replace("Exibir o rótulo com acento.", "Exibir o rótulo correto."))
        self.assertEqual(self.invoke("allocate-id", self.id, "REQ")["id"], "REQ-003")
        self.assertEqual(self.invoke("allocate-id", self.id, "AC")["id"], "AC-002")
        self.assertTrue(self.invoke("validate", self.id)["valid"])

    def test_an_orphaned_reference_is_not_reallocated_to_an_unrelated_requirement(self):
        self.write_contract(spec=SPEC.replace("- REQ-001: Exibir o rótulo com acento.\n", ""))
        new_id = self.invoke("allocate-id", self.id, "REQ")["id"]
        self.assertEqual(new_id, "REQ-002")
        new_spec = SPEC.replace("REQ-001: Exibir o rótulo com acento.", f"{new_id}: Habilitar o filtro.")
        (self.folder / "spec.md").write_bytes(new_spec.encode("utf-8"))
        errors = self.invoke("validate", self.id, code=1)["diagnostics"]
        self.assertIn("unknown_reference", {error["code"] for error in errors})

    def test_a_completed_lite_task_must_validate_its_new_full_contract(self):
        lite = self.invoke("new", "--title", "Correção curta", "--mode", "lite")
        evidence = f"{lite['path']}/tarefa.md"
        self.invoke("set-status", lite["id"], "verified", "--manual-evidence", evidence)
        self.invoke("set-status", lite["id"], "completed")
        promoted = self.invoke("mode", lite["id"], "full")
        self.assertEqual(promoted["status"], "in_progress")
        self.assertIn("sdd validate", self.invoke("set-status", lite["id"], "completed", code=2))
        backup = self.root / promoted["backup"] / "meta.json"
        self.assertEqual(json.loads(backup.read_bytes())["status"], "completed")

    def test_markdown_examples_do_not_declare_items_and_links_stay_local(self):
        spec = SPEC.replace("## Critérios", "~~~markdown\n- REQ-001: Exemplo.\n~~~\n"
                            "<!--\n- REQ-001: Exemplo oculto.\n-->\n\n## Critérios")
        spec = spec.replace("Exibir o rótulo correto.", "Exibir o rótulo correto com o literal \x60<!--\x60.")
        plan = PLAN.replace("Tela de configuração.", "[Objetivo](spec.md#objetivo) e [externo](https://example.com).")
        self.write_contract(spec=spec, plan=plan)
        self.assertTrue(self.invoke("validate", self.id)["valid"])
        (self.folder / "plan.md").write_bytes(plan.replace("#objetivo", "#anonimo").encode("utf-8"))
        errors = self.invoke("validate", self.id, code=1)["diagnostics"]
        self.assertEqual([error["code"] for error in errors], ["broken_link"])

    def test_markdown_bullet_variants_cannot_hide_pending_steps(self):
        for marker in ("*", "+", "1."):
            with self.subTest(marker=marker):
                self.write_contract(tasks=TASKS.replace(
                    "## Verificação", f"{marker} [ ] T-002 (REQ-001, AC-001): Conferir em outra resolução.\n\n## Verificação"
                ))
                report = self.invoke("trace", self.id)
                self.assertEqual(report["pending_tasks"], ["T-002"])
        self.write_contract(tasks=TASKS + "\n## Notas\n- [ ] T-002 (REQ-001, AC-001): Corrigir legenda.\n")
        self.assertIn("wrong_section", {item["code"] for item in self.invoke("validate", self.id, code=1)["diagnostics"]})
        self.write_contract(tasks=TASKS.replace(
            "## Verificação", "    - [ ]  T-002 (REQ-001, AC-001): Subpasso pendente.\n\n## Verificação"
        ))
        self.assertIn("indented_entry", {item["code"] for item in self.invoke("validate", self.id, code=1)["diagnostics"]})

    def test_spec_entries_outside_their_sections_block_validation_and_approval(self):
        extra = "- REQ-001: Regra conflitante.\n- AC-002 (REQ-001): Resultado adicional."
        spec = SPEC.replace("O campo mantém seu valor ao editar.", extra)
        self.write_contract(spec=spec)
        errors = self.invoke("validate", self.id, code=1)["diagnostics"]
        self.assertEqual([error["code"] for error in errors], ["wrong_section", "wrong_section"])
        digest = sha256((self.folder / "spec.md").read_bytes()).hexdigest()
        self.assertIn("Declare REQ", self.invoke("approve", self.id, code=2, confirmation=digest))

    def test_links_in_code_labels_and_reference_definitions_are_checked(self):
        for broken in (
            "[\x60arquivo\x60](nao-existe.py)",
            "[prova][resultado]\n\n[resultado]: nao-existe.py",
            "[prova][resultado]",
        ):
            with self.subTest(broken=broken):
                self.write_contract(plan=PLAN.replace("Tela de configuração.", broken))
                errors = self.invoke("validate", self.id, code=1)["diagnostics"]
                self.assertTrue(any(error["code"] == "broken_link" and error["file"] == "plan.md" for error in errors))
        self.write_contract(plan=PLAN.replace("Tela de configuração.", r"\[literal](nao-existe.py)"))
        self.assertTrue(self.invoke("validate", self.id)["valid"])
