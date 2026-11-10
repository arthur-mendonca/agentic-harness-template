"""Prepare projects or explicitly install global skills without running checks."""

import argparse
import difflib
import json
from pathlib import Path
import re
import sys
import tomllib
import uuid

from harness import __version__
from harness.config import ConfigError, contained_path, load_config, read_json, validate_config
from harness.project import PROJECT_FILES

SKILLS = ("verified-development", "code-investigation", "tdd-implementation", "adversarial-review", "http-homologation")
CONVENTIONAL = ("prepare", "lint", "types", "test", "build")


def _configured(command):
    return {"state": "configured", "command": command, "cwd": ".", "timeout": 300}


def inspect_project(root):
    entries = sorted(p.name for p in root.iterdir())
    detected = {"languages": [], "frameworks": [], "managers": [], "evidence": [], "existing": entries}
    checks = {name: {"state": "unconfigured", "reason": "No command identified safely; inspect and configure manually"} for name in CONVENTIONAL}
    checks["prepare"]["reason"] = "Dependency installation and preparation require explicit authorization; configure manually"
    markers = {"Cargo.toml": ("Rust", "cargo"), "go.mod": ("Go", "go"),
               "pom.xml": ("Java", "maven"), "build.gradle": ("JVM", "gradle"),
               "Gemfile": ("Ruby", "bundler"), "composer.json": ("PHP", "composer")}
    for marker, (language, manager) in markers.items():
        if (root / marker).is_file():
            detected["languages"].append(language)
            detected["managers"].append(manager)
            detected["evidence"].append(marker)
    if any(p.suffix in (".csproj", ".fsproj", ".sln") for p in root.iterdir()):
        detected["languages"].append(".NET")
        detected["managers"].append("dotnet")
    if (root / "package.json").is_file():
        package = read_json(root / "package.json")
        if not isinstance(package, dict) or not isinstance(package.get("scripts", {}), dict):
            raise ConfigError("package.json and its scripts must be objects")
        detected["languages"].append("JavaScript/TypeScript")
        detected["evidence"].append("package.json scripts")
        dependencies = package.get("dependencies", {})
        dev_dependencies = package.get("devDependencies", {})
        if not isinstance(dependencies, dict) or not isinstance(dev_dependencies, dict):
            raise ConfigError("package.json dependencies must be objects")
        detected["frameworks"].extend(sorted(set(dependencies) | set(dev_dependencies)))
        declared = package.get("packageManager", "")
        manager = declared.split("@", 1)[0] if isinstance(declared, str) else ""
        locks = {name for name, filename in (("npm", "package-lock.json"), ("yarn", "yarn.lock"),
                 ("pnpm", "pnpm-lock.yaml"), ("bun", "bun.lock"), ("bun", "bun.lockb")) if (root / filename).is_file()}
        if not declared:
            manager = next(iter(locks)) if len(locks) == 1 else ("npm" if not locks else "")
        if manager not in ("npm", "yarn", "pnpm", "bun"):
            manager = ""
        detected["managers"].extend([manager] if manager else sorted(locks))
        for check, names in {"lint": ("lint",), "types": ("types", "typecheck", "type-check"), "test": ("test",), "build": ("build",)}.items():
            script = next((name for name in names if name in package.get("scripts", {})), None)
            if script:
                command = package["scripts"][script]
                if manager and isinstance(command, str) and command.strip() and "no test specified" not in command:
                    checks[check] = _configured([manager, "run", script])
                else:
                    checks[check]["reason"] = "Ambiguous package manager or missing/placeholder script"
    pyproject = {}
    if (root / "pyproject.toml").is_file():
        try:
            pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as exc:
            raise ConfigError(f"Invalid pyproject.toml: {exc}") from exc
        detected["languages"].append("Python")
        detected["managers"].append("pip")
        detected["evidence"].append("pyproject.toml")
    tools = pyproject.get("tool", {})
    if not isinstance(tools, dict):
        raise ConfigError("pyproject.toml tool must be a table")
    for check, tool, marker, argv in (
        ("test", "pytest", "pytest.ini", ["python", "-m", "pytest"]),
        ("lint", "ruff", "ruff.toml", ["python", "-m", "ruff", "check", "."]),
        ("types", "mypy", "mypy.ini", ["python", "-m", "mypy", "."]),
    ):
        if tool in tools or (root / marker).is_file():
            if checks[check]["state"] != "configured":
                checks[check] = _configured(argv)
            detected["evidence"].append(f"{tool} configuration")
    if (root / "Makefile").is_file():
        makefile = (root / "Makefile").read_text(encoding="utf-8-sig")
        targets = set(re.findall(r"^([A-Za-z0-9_-]+)\s*:(?!=)", makefile, re.MULTILINE))
        for name in ("lint", "types", "test", "build"):
            if name in targets and checks[name]["state"] != "configured":
                checks[name] = _configured(["make", name])
                detected["evidence"].append(f"Makefile target {name}")
        detected["managers"].append("make")
    return detected, checks


def _preflight(root, files, directories):
    for relative in directories:
        path = contained_path(root, relative)
        if path.exists() and not path.is_dir():
            raise ConfigError(f"Expected a directory, preserved conflicting path: {path}")
    for relative in files:
        path = contained_path(root, relative)
        if path.exists() and not path.is_file():
            raise ConfigError(f"Expected a file, preserved conflicting path: {path}")
        # Do not change a different file through an existing symlink.
        if (root / relative).is_symlink():
            raise ConfigError(f"Refusing to write through a symlink: {relative}")


def init_project(project):
    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        raise ConfigError(f"Destination must be an existing directory: {root}")
    _preflight(root, (*PROJECT_FILES, ".harness/harness.json", "harness.json", ".gitignore"), (".harness", ".harness/planos", ".harness/memoria", ".harness/results"))
    inspection, checks = inspect_project(root)
    config = {"schema_version": 1, "harness_version": __version__, "project": root.name, "checks": checks}
    validate_config(config, root)
    if (root / "harness.json").exists() or (root / ".harness/harness.json").exists():
        load_config(root)  # Fail before writing anything if the preserved config is incompatible.
    proposals = dict(PROJECT_FILES)
    for directory in ("planos", "memoria"):
        if (root / directory).exists() and not (root / ".harness" / directory).exists():
            proposals = {name: text for name, text in proposals.items() if not name.startswith(f".harness/{directory}/")}
    if not (root / "harness.json").exists() or (root / ".harness/harness.json").exists():
        proposals[".harness/harness.json"] = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    summary = {"root": str(root), "created": [], "preserved": [], "updated": [], "differences": {},
               "legacy_files": [name for name in ("harness.json", "planos", "memoria", "tarefas/pendencias.md") if (root / name).exists()],
               "inspection": inspection, "configured": [], "pending": [], "valid": False, "checks_executed": False}
    # Read and compare all preserved files before mutating the destination.
    for name, text in proposals.items():
        path = root / name
        if path.exists():
            previous = path.read_text(encoding="utf-8-sig")
            summary["preserved"].append(name)
            if previous != text:
                summary["differences"][name] = list(difflib.unified_diff(
                    previous.splitlines(), text.splitlines(), fromfile=f"existing/{name}", tofile=f"proposed/{name}", lineterm=""))
    ignore = root / ".gitignore"
    ignore_existed = ignore.exists()
    previous_ignore = ignore.read_bytes() if ignore_existed else b""
    patterns = [line.strip() for line in previous_ignore.decode("utf-8-sig").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    directories = {str(Path(name).parent).replace("\\", "/") for name in proposals if "/" in name}
    for relative in sorted(directories | {".harness/results"}):
        path = root / relative
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            summary["created"].append(relative + "/")
    for name, text in proposals.items():
        path = root / name
        if not path.exists():
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
            summary["created"].append(name)
    if not patterns or patterns[-1] not in (".harness/", "/.harness/"):
        with ignore.open("ab") as stream:
            stream.write((b"\n" if previous_ignore and not previous_ignore.endswith(b"\n") else b"") + b".harness/\n")
        summary["updated" if ignore_existed else "created"].append(".gitignore")
    else:
        summary["preserved"].append(".gitignore")
    final = load_config(root)
    summary["configured"] = [name for name, check in final["checks"].items() if check["state"] == "configured"]
    summary["pending"] = [name for name, check in final["checks"].items() if check["state"] == "unconfigured"]
    summary["valid"] = True
    return summary


def install_skills(destination=None, update=False, source=None):
    root = Path(destination if destination is not None else Path.home() / ".agents" / "skills").expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise ConfigError(f"Skills destination is not a directory: {root}")
    _preflight(root, [f"{name}/SKILL.md" for name in SKILLS], SKILLS)
    source_root = Path(source if source is not None else Path(__file__).resolve().parent.parent / "skills").expanduser().resolve()
    # Skill files are read only by this explicit copy operation, never by init/run.
    sources = {}
    for name in SKILLS:
        source_file = contained_path(source_root, f"{name}/SKILL.md")
        if not source_file.is_file():
            raise ConfigError(f"Skill source missing: {source_file}. Supply --source PATH_TO_SKILLS from the source checkout")
        sources[name] = source_file.read_text(encoding="utf-8")
    summary = {"source": str(source_root), "destination": str(root), "version": __version__, "created": [], "preserved": [],
               "updated": [], "backups": [], "conflicts": []}
    for name, text in sources.items():
        target = root / name / "SKILL.md"
        if target.exists():
            previous = target.read_bytes()
            if previous == text.encode("utf-8"):
                summary["preserved"].append(name)
                continue
            if not update:
                summary["conflicts"].append(name)
                continue
            backup = target.with_name(f"SKILL.md.backup-{uuid.uuid4().hex}")
            with backup.open("xb") as stream:
                stream.write(previous)
            summary["backups"].append(str(backup))
            summary["updated"].append(name)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            summary["created"].append(name)
        target.write_text(text, encoding="utf-8", newline="\n")
    return summary


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Also accept `python setup.py PATH` as the direct installation interface.
    if argv and argv[0] not in ("init", "skills", "-h", "--help", "--version"):
        argv.insert(0, "init")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    init = subparsers.add_parser("init", help="Inspect and prepare an existing project directory")
    init.add_argument("project")
    skills = subparsers.add_parser("skills", help="Explicitly install the five global Agent Skills")
    skills.add_argument("--source", help="Source skills directory; default: skills/ next to the source harness directory")
    skills.add_argument("--destination", help="Default: ~/.agents/skills/")
    skills.add_argument("--update", action="store_true", help="Replace differing SKILL.md files, preserving backups")
    args = parser.parse_args(argv)
    try:
        result = init_project(args.project) if args.operation == "init" else install_skills(args.destination, args.update, args.source)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3 if result.get("conflicts") else 0
    except (ConfigError, OSError, UnicodeError) as exc:
        print(f"Installation error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
