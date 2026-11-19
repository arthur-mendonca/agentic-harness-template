import contextlib
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from harness.config import load_config
from harness.installer import init_project
from harness.runner import main, run
from tests.helpers import temporary_project
from tests.test_specs import PLAN, SPEC, TASKS, _Terminal


class ConvergenceTests(unittest.TestCase):
    def setUp(self):
        directory = temporary_project()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        init_project(self.root)
        task = self.invoke("new", "--mode", "full", "--title", "Conferir critérios")
        self.id, self.folder = task["id"], self.root / task["path"]
        self.documents = {
            "spec.md": SPEC.replace("## Restrições", "- AC-002 (REQ-001): O formulário preserva os dados.\n\n## Restrições"),
            "plan.md": PLAN + "- AC-002: Edite o formulário e compare os dados.\n",
            "tasks.md": TASKS.replace("(REQ-001, AC-001)", "(REQ-001, AC-001, AC-002)"),
        }
        for file, content in self.documents.items():
            (self.folder / file).write_bytes(content.encode("utf-8"))
        config = load_config(self.root)
        config["checks"] = {
            "label": self.check("print('label ok')"),
            "form": self.check("raise SystemExit(1)"),
            "broken": {**self.check(""), "command": [str(self.root / "missing-executable")]},
            "pending": {"state": "unconfigured", "reason": "Missing test environment"},
            "optional": {"state": "not_applicable", "reason": "No interface"},
        }
        (self.root / ".harness/harness.json").write_text(json.dumps(config), encoding="utf-8")
        self.contract = self.invoke("verify", self.id, code=1)["contract"]
        self.review = {"status": "not_performed", "reason": "Independent reviewer unavailable"}
        self.manual = "manual.txt"
        (self.root / self.manual).write_text("Edited the form and compared the saved fields.", encoding="utf-8")

    def check(self, command):
        return {"state": "configured", "command": [sys.executable, "-c", command], "cwd": ".", "timeout": 10}

    def invoke(self, *args, code=0, confirmation=None):
        output = io.StringIO()
        errors = _Terminal() if confirmation is not None else io.StringIO()
        stdin = _Terminal(confirmation + "\n") if confirmation is not None else io.StringIO()
        with (contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors),
              patch("harness.sdd_cli.sys.stdin", stdin)):
            result = main(["sdd", "--project", str(self.root), *args])
        self.assertEqual(result, code, output.getvalue() + errors.getvalue())
        return json.loads(output.getvalue()) if output.getvalue() else errors.getvalue()

    def report(self, *checks):
        _, _, path = run(self.root, checks)
        return path.relative_to(self.root).as_posix()

    def criterion(self, status, *evidence):
        return {"status": status, "reason": "Compared the criterion against its planned verification.",
                "evidence": list(evidence)}

    def assess(self, criteria, *, code=0, review=None):
        path = self.root / "assessment.json"
        path.write_text(json.dumps({"contract": self.contract, "criteria": criteria,
                                    "review": self.review if review is None else review}), encoding="utf-8")
        return self.invoke("verify", self.id, "--assessment", str(path), code=code)

    def test_green_suite_leaves_unmapped_criteria_unverified(self):
        report = self.report("label")
        self.invoke("set-status", self.id, "verified", "--evidence", report)
        self.assertIn("sdd verify", self.invoke("set-status", self.id, "completed", code=2))
        outcome = self.assess({"AC-001": self.criterion("met", {"report": report, "check": "label"})}, code=1)
        self.assertEqual(outcome["criteria"]["AC-001"]["status"], "met")
        self.assertEqual(outcome["criteria"]["AC-002"]["status"], "unverified")
        self.assertEqual(outcome["review"]["status"], "not_performed")
        self.assertIn("AC-002", self.invoke("set-status", self.id, "completed", code=2))

    def test_reassessment_distinguishes_failures_and_blockers_from_a_passing_check(self):
        report = self.report("label", "form", "pending", "optional", "broken")
        good = self.criterion("met", {"report": report, "check": "label"})
        for check, status in (("form", "divergent"), ("pending", "blocked"),
                              ("optional", "unverified"), ("broken", "blocked")):
            with self.subTest(check=check):
                outcome = self.assess({"AC-001": good, "AC-002": self.criterion(
                    "met", {"report": report, "check": check})}, code=1)
                self.assertEqual(outcome["criteria"]["AC-001"]["status"], "met")
                self.assertEqual(outcome["criteria"]["AC-002"]["status"], status)
        unselected = self.report("label")
        for claim in ("met", "divergent"):
            outcome = self.assess({"AC-001": good, "AC-002": self.criterion(
                claim, {"report": unselected, "check": "form"})}, code=1)
            self.assertEqual(outcome["criteria"]["AC-002"]["status"], "unverified")
            self.assertEqual(outcome["criteria"]["AC-002"]["evidence"][0]["result"], "not_run")
        outcome = self.assess({"AC-001": good, "AC-002": self.criterion("met", {"file": self.manual})})
        self.assertTrue(outcome["ready"])
        self.assertEqual(self.invoke("set-status", self.id, "completed")["status"], "completed")

    def test_review_findings_and_unfinished_steps_block_closure(self):
        proof = self.criterion("met", {"file": self.manual})
        criteria = {"AC-001": proof, "AC-002": proof}
        outcome = self.assess(criteria, code=1, review={"status": "findings", "reason": "A regression remains."})
        self.assertFalse(outcome["ready"])
        self.assertIn("review", self.invoke("set-status", self.id, "completed", code=2))
        (self.folder / "tasks.md").write_bytes(self.documents["tasks.md"].replace("[x]", "[ ]").encode("utf-8"))
        self.assertIn("Contract changed", self.assess(criteria, code=2))
        self.contract = self.invoke("verify", self.id, code=1)["contract"]
        self.assertEqual(self.assess(criteria, code=1)["pending_tasks"], ["T-001"])
        self.assertIn("T-001", self.invoke("set-status", self.id, "completed", code=2))

    def test_changed_or_missing_evidence_invalidates_its_criterion_and_completion(self):
        report = self.report("label")
        self.assess({"AC-001": self.criterion("met", {"report": report, "check": "label"}),
                     "AC-002": self.criterion("met", {"file": self.manual})})
        self.invoke("set-status", self.id, "completed")
        (self.root / report).unlink()
        status = self.invoke("status", self.id)
        self.assertTrue(status["completion_stale"])
        self.assertEqual(status["verification"], "unverified")
        outcome = self.invoke("verify", self.id, code=1)
        self.assertEqual(outcome["criteria"]["AC-001"]["status"], "unverified")
        self.assertEqual(outcome["criteria"]["AC-002"]["status"], "met")

    def test_reopening_invalidates_the_assessment_and_lite_requires_its_own_verification(self):
        proof = self.criterion("met", {"file": self.manual})
        criteria = {"AC-001": proof, "AC-002": proof}
        self.assess(criteria)
        self.invoke("set-status", self.id, "completed")
        self.assess(criteria)
        self.assertEqual(self.invoke("status", self.id)["status"], "completed")
        self.invoke("set-status", self.id, "blocked")
        self.assertFalse(self.invoke("verify", self.id, code=1)["assessment_current"])
        self.assertIn("sdd verify", self.invoke("set-status", self.id, "verified", code=2))
        self.assess(criteria)
        self.invoke("set-status", self.id, "completed")
        lite = self.invoke("mode", self.id, "lite")
        self.assertEqual((lite["status"], lite["verification"]), ("in_progress", "unverified"))
        backup = self.root / lite["backup"] / "meta.json"
        self.assertIn("convergence", json.loads(backup.read_bytes()))

    def test_verified_state_reflects_changed_evidence_before_completion(self):
        proof = self.criterion("met", {"file": self.manual})
        self.assess({"AC-001": proof, "AC-002": proof})
        (self.root / self.manual).write_text("Different result", encoding="utf-8")
        for command in ("status", "resume"):
            self.assertEqual(self.invoke(command, self.id)["verification"], "unverified")
        self.assertEqual(self.invoke("list")["tasks"][0]["verification"], "unverified")
        self.assertIn("AC-001", self.invoke("set-status", self.id, "completed", code=2))

    def test_invalid_assessment_cannot_replace_a_current_one(self):
        report = self.report("label")
        checked = self.criterion("met", {"report": report, "check": "label"})
        good = {"AC-001": checked, "AC-002": self.criterion("met", {"file": self.manual})}
        self.assess(good)
        for criterion, message in (
            ({"AC-999": checked}, "Unknown acceptance criterion"),
            ({"AC-001": self.criterion("met", {"file": report})}, "check report"),
            ({"AC-001": self.criterion("met", {"file": report.removesuffix(".json") + ".log"})}, "check report"),
            ({"AC-001": self.criterion("met", {"file": "../outside.txt"})}, "Unsafe"),
        ):
            with self.subTest(criterion=criterion):
                self.assertIn(message, self.assess(criterion, code=2))
                self.assertTrue(self.invoke("verify", self.id)["ready"])

    @unittest.skipUnless(os.name == "nt", "Windows normalizes trailing dots and spaces")
    def test_windows_path_aliases_cannot_turn_runner_artifacts_into_manual_evidence(self):
        report = self.report("label")
        aliases = (report.replace("/results/", "/results./"), report.removesuffix(".json") + ".log.")
        for alias in aliases:
            with self.subTest(alias=alias):
                self.assertIn("check report", self.assess(
                    {"AC-001": self.criterion("met", {"file": alias})}, code=2,
                ))

    def test_assessment_respects_pending_decisions_and_the_approved_specification(self):
        proof = self.criterion("met", {"file": self.manual})
        criteria = {"AC-001": proof, "AC-002": proof}
        self.invoke("await-decision", self.id)
        self.assertIn("pending decisions", self.assess(criteria, code=2))
        specification = self.folder / "spec.md"
        digest = sha256(specification.read_bytes()).hexdigest()
        self.assertEqual(self.invoke("approve", self.id, confirmation=digest)["spec_status"], "approved")
        self.assess(criteria)
        self.invoke("set-status", self.id, "completed")
        specification.write_bytes(self.documents["spec.md"].replace("Uma tela", "Duas telas").encode("utf-8"))
        outcome = self.invoke("verify", self.id, code=1)
        self.assertEqual(outcome["spec_status"], "awaiting_decision")
        self.assertFalse(outcome["assessment_current"])
