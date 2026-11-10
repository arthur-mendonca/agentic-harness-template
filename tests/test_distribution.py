import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import unittest
import zipfile

from tests.helpers import temporary_project


class DistributionTests(unittest.TestCase):
    def test_editable_build_dispatches_to_setuptools_without_importing_package(self):
        setup_path = Path(__file__).resolve().parents[1] / "setup.py"
        script = '''
import runpy
import sys
import types
fake = types.ModuleType("setuptools")
fake.setup = lambda: print("setuptools invoked")
sys.modules["setuptools"] = fake
sys.argv = [sys.argv[1], "editable_wheel"]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
        result = subprocess.run([sys.executable, "-I", "-c", script, str(setup_path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "setuptools invoked")

    def test_wheel_generates_controls_and_runs_outside_checkout(self):
        wheel_dir = Path(os.environ.get("HARNESS_WHEEL_DIR", Path(__file__).resolve().parents[1] / ".harness/wheels"))
        wheels = list(wheel_dir.glob("*.whl"))
        if not wheels:
            if os.environ.get("HARNESS_TEST_WHEEL"):
                self.fail("Wheel required but absent: build it with python -m pip wheel . --no-deps -w .harness/wheels")
            self.skipTest("Build a wheel in .harness/wheels/ to exercise installed-package isolation")
        self.assertEqual(len(wheels), 1, "Use one release wheel in .harness/wheels/ for an unambiguous installation")
        with zipfile.ZipFile(wheels[0]) as archive:
            self.assertFalse(any(name.endswith("SKILL.md") or name.startswith("harness_skills/") for name in archive.namelist()))
            self.assertFalse(any(name.startswith(("templates/", "harness_templates/")) for name in archive.namelist()))
        with temporary_project() as directory:
            root = Path(directory)
            site = root / "site"
            installed = subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-index", "--target", str(site), str(wheels[0])], capture_output=True, text=True)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            project = root / "consumer"
            project.mkdir()
            script = '''
import importlib.metadata
import json
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
import harness
from harness.installer import init_project
from harness.runner import run
assert Path(harness.__file__).is_relative_to(Path(sys.argv[1]))
assert importlib.metadata.version("agentic-verifiable-harness") == harness.__version__
entries = importlib.metadata.distribution("agentic-verifiable-harness").entry_points
assert {entry.name for entry in entries} == {"harness", "harness-setup"}
for entry in entries:
    assert callable(entry.load())
project = Path(sys.argv[2])
assert init_project(project)["valid"]
assert {p.name for p in (project / ".harness/planos").iterdir()} == {"instrucoes.md", "pendencias.md", "relatorios.md"}
assert not (project / "tarefas").exists()
assert {p.name for p in (project / ".harness/memoria").iterdir()} == {"regras-negocio.md", "problemas-conhecidos.md", "decisoes.md"}
config = json.loads((project / ".harness/harness.json").read_text(encoding="utf-8"))
config["checks"] = {"smoke": {"state": "configured", "command": [sys.executable, "-c", "print('installed-wheel-ok')"], "cwd": ".", "timeout": 5}}
(project / ".harness/harness.json").write_text(json.dumps(config), encoding="utf-8")
report, code, path = run(project, ["smoke"])
assert code == 0, report
assert report["checks"]["smoke"]["stdout"].strip() == "installed-wheel-ok"
assert not (Path(sys.argv[1]) / "harness_skills").exists()
assert not (project / "skills").exists()
print(json.dumps({"installed_package": harness.__file__, "evidence": str(path), "status": "passed"}))
'''
            result = subprocess.run([sys.executable, "-I", "-c", script, str(site), str(project)], cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "passed")

    def test_copied_runtime_works_without_external_resources(self):
        with temporary_project() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            runtime = root / "copied-runtime"
            shutil.copytree(source / "harness", runtime / "harness", ignore=shutil.ignore_patterns("__pycache__"))
            project = root / "consumer"
            project.mkdir()
            script = '''
import json
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from harness.installer import init_project
from harness.runner import run
project = Path(sys.argv[2])
assert not (Path(sys.argv[1]) / "skills").exists()
assert not (Path(sys.argv[1]) / "templates").exists()
assert init_project(project)["valid"]
assert {p.name for p in (project / ".harness/planos").iterdir()} == {"instrucoes.md", "pendencias.md", "relatorios.md"}
assert {p.name for p in (project / ".harness/memoria").iterdir()} == {"regras-negocio.md", "problemas-conhecidos.md", "decisoes.md"}
config = json.loads((project / ".harness/harness.json").read_text(encoding="utf-8"))
config["checks"] = {"copied": {"state": "configured", "command": [sys.executable, "-c", "print('copied-runtime-ok')"], "cwd": ".", "timeout": 5}}
(project / ".harness/harness.json").write_text(json.dumps(config), encoding="utf-8")
report, code, path = run(project, ["copied"])
assert code == 0, report
assert report["checks"]["copied"]["stdout"].strip() == "copied-runtime-ok"
'''
            result = subprocess.run([sys.executable, "-I", "-c", script, str(runtime), str(project)], cwd=project, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
