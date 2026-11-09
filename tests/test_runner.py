import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

from harness import __version__
from harness.config import ConfigError, discover_root
from harness.runner import main, run
from tests.helpers import directory_link, temporary_project


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_project()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = {"schema_version": 1, "harness_version": __version__, "project": "fixture", "checks": {}}

    def command(self, source, **kwargs):
        return {"state": "configured", "command": [sys.executable, "-c", source], "cwd": ".", "timeout": 5, **kwargs}

    def execute(self, checks=None):
        (self.root / "harness.json").write_text(json.dumps(self.data), encoding="utf-8")
        return run(self.root, checks)

    def test_success_failure_timeout_and_evidence(self):
        self.data["checks"] = {
            "success": self.command("import sys; print('output'); print('error-stream', file=sys.stderr)"),
            "failure": self.command("raise SystemExit(7)"),
            "slow": self.command("import time; print('started', flush=True); time.sleep(10)", timeout=0.2),
        }
        report, code, path = self.execute(["success", "failure", "slow"])
        self.assertEqual(code, 1)
        results = report["checks"]
        self.assertEqual([results[n]["status"] for n in self.data["checks"]], ["passed", "failed", "timeout"])
        self.assertEqual(results["failure"]["returncode"], 7)
        self.assertIn("output", results["success"]["stdout"])
        self.assertIn("error-stream", results["success"]["stderr"])
        self.assertIn("started", results["slow"]["stdout"])
        self.assertGreater(results["success"]["duration_seconds"], 0)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), report)
        log = path.with_suffix(".log").read_text(encoding="utf-8")
        self.assertIn("timeout", log)
        self.assertIn("error-stream", log)

    def test_selection_and_all_six_statuses(self):
        self.data["checks"] = {
            "test": self.command("pass"), "build": self.command("raise SystemExit(9)"),
            "lint": {"state": "unconfigured", "reason": "No tool identified"},
            "types": {"state": "not_applicable", "reason": "No static type check in this project"},
        }
        report, code, _ = self.execute(["test"])
        self.assertEqual(code, 0)
        self.assertEqual(report["checks"]["test"]["status"], "passed")
        self.assertEqual(report["checks"]["build"]["status"], "not_run")
        self.assertEqual(report["checks"]["lint"]["status"], "unconfigured")
        self.assertEqual(report["checks"]["types"]["status"], "not_applicable")
        self.assertEqual(self.execute(["lint"])[1], 3)
        self.assertEqual(self.execute(["types"])[1], 0)

    def test_no_selection_never_executes(self):
        self.data["checks"]["danger"] = self.command("from pathlib import Path; Path('executed').touch()")
        report, code, _ = self.execute()
        self.assertEqual(code, 3)
        self.assertEqual(report["checks"]["danger"]["status"], "not_run")
        self.assertFalse((self.root / "executed").exists())

    def test_working_directory_and_discovery(self):
        sub = self.root / "sub dir"
        sub.mkdir()
        self.data["checks"]["cwd"] = self.command("from pathlib import Path; print(Path.cwd().name)", cwd="sub dir")
        report, code, _ = self.execute(["cwd"])
        self.assertEqual(code, 0)
        self.assertEqual(report["checks"]["cwd"]["stdout"].strip(), "sub dir")
        previous = Path.cwd()
        try:
            os.chdir(sub)
            self.assertEqual(discover_root(), self.root)
        finally:
            os.chdir(previous)
        with self.assertRaises(ConfigError):
            discover_root(sub)  # Explicit path does not silently target a parent.

    def test_relative_executable_is_resolved_from_check_working_directory(self):
        sub = self.root / "sub"
        sub.mkdir()
        filename = "local-check.cmd" if os.name == "nt" else "local-check"
        script = sub / filename
        script.write_text("@echo relative-check-ok\n" if os.name == "nt" else "#!/bin/sh\nprintf 'relative-check-ok\\n'\n", encoding="utf-8")
        script.chmod(0o755)
        self.data["checks"]["local"] = self.command("pass", command=[f"./{filename}"], cwd="sub")
        report, code, _ = self.execute(["local"])
        self.assertEqual(code, 0, report)
        self.assertIn("relative-check-ok", report["checks"]["local"]["stdout"])

    def test_missing_executable_is_failed_and_remaining_checks_run(self):
        self.data["checks"] = {"absent": self.command("pass", command=["harness-nonexistent-987654"]), "ok": self.command("pass")}
        report, code, _ = self.execute(["absent", "ok"])
        self.assertEqual(code, 1)
        self.assertEqual(report["checks"]["absent"]["status"], "failed")
        self.assertIsNone(report["checks"]["absent"]["returncode"])
        self.assertTrue(report["checks"]["absent"]["stderr"])
        self.assertEqual(report["checks"]["ok"]["status"], "passed")

    def test_unknown_selection_validated_before_execution(self):
        self.data["checks"]["ok"] = self.command("from pathlib import Path; Path('executed').touch()")
        self.execute()
        with self.assertRaises(ConfigError):
            run(self.root, ["ok", "unknown"])
        self.assertFalse((self.root / "executed").exists())

    def test_cli_exit_codes_and_validate_list_all(self):
        self.data["checks"] = {"ok": self.command("pass"), "bad": self.command("raise SystemExit(1)")}
        self.execute()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--project", str(self.root), "--check", "ok"]), 0)
            self.assertEqual(main(["--project", str(self.root), "--all"]), 1)
            self.assertEqual(main(["--project", str(self.root), "--check", "unknown"]), 2)
            self.assertEqual(main(["--project", str(self.root)]), 3)
            self.assertEqual(main(["--project", str(self.root), "--validate"]), 0)
            self.assertEqual(main(["--project", str(self.root), "--list"]), 0)

    def test_version_mismatch_prevents_command_execution(self):
        self.data["harness_version"] = "9.9.9"
        self.data["checks"]["ok"] = self.command("from pathlib import Path; Path('executed').touch()")
        with self.assertRaises(ConfigError):
            self.execute(["ok"])
        self.assertFalse((self.root / "executed").exists())

    def test_module_entry_point(self):
        self.execute()
        process = subprocess.run([sys.executable, "-m", "harness.runner", "--project", str(self.root), "--validate"], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_unique_reports(self):
        self.data["checks"]["ok"] = self.command("pass")
        first = self.execute(["ok"])[2]
        second = self.execute(["ok"])[2]
        self.assertNotEqual(first, second)
        self.assertTrue(first.is_file())

    def test_empty_and_space_arguments_are_preserved(self):
        command = [sys.executable, "-c", "import sys; print(repr(sys.argv[1:]))", "", " "]
        self.data["checks"]["arguments"] = self.command("pass", command=command)
        report, code, _ = self.execute(["arguments"])
        self.assertEqual(code, 0)
        self.assertEqual(report["checks"]["arguments"]["stdout"].strip(), "['', ' ']")

    def test_selected_checks_follow_requested_order(self):
        self.data["checks"] = {
            "verify": self.command("from pathlib import Path; assert Path('ready').exists()"),
            "prepare": self.command("from pathlib import Path; Path('ready').touch()"),
        }
        self.assertEqual(self.execute(["prepare", "verify"])[1], 0)

    def test_timeout_stops_child_process(self):
        child = "import time; from pathlib import Path; time.sleep(1); Path('child-survived').touch()"
        parent = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child!r}]); print('spawned', flush=True); time.sleep(10)"
        self.data["checks"]["tree"] = self.command(parent, timeout=0.3)
        report, code, _ = self.execute(["tree"])
        self.assertEqual(code, 1)
        self.assertEqual(report["checks"]["tree"]["status"], "timeout")
        self.assertIn("spawned", report["checks"]["tree"]["stdout"])
        time.sleep(1.1)
        self.assertFalse((self.root / "child-survived").exists())

    def test_results_link_cannot_write_outside_project(self):
        project = self.root / "project"
        project.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (project / "harness.json").write_text(json.dumps(self.data), encoding="utf-8")
        directory_link(project / ".harness", outside)
        with self.assertRaises(ConfigError):
            run(project)
        self.assertEqual(list(outside.iterdir()), [])
