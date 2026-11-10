"""Run explicitly selected commands and persist evidence for every check."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

from harness import __version__
from harness.config import ConfigError, contained_path, discover_root, load_config


def _terminate(process):
    if os.name == "nt":
        # Windows has no killpg. taskkill also stops children holding log handles.
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except OSError:
            pass  # The direct process is still terminated below.
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait()


def _execute(root, check, work):
    command = check["command"].copy()
    cwd = contained_path(root, check["cwd"])
    if not Path(command[0]).is_absolute() and os.path.dirname(command[0]):
        # CreateProcess on Windows otherwise resolves paths using the caller's cwd.
        command[0] = str((cwd / command[0]).resolve())
    if os.name == "nt":
        command[0] = shutil.which(command[0]) or command[0]
    result = {"status": "failed", "command": check["command"], "cwd": str(cwd),
              "timeout": check["timeout"], "returncode": None,
              "stdout": "", "stderr": "", "duration_seconds": 0.0}
    started = time.perf_counter()
    # Files avoid pipe deadlocks and preserve partial output on a timeout.
    out_path, err_path = work / "stdout.tmp", work / "stderr.tmp"
    try:
        with out_path.open("wb") as out, err_path.open("wb") as err:
            process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=err, shell=False,
                                       start_new_session=(os.name != "nt"))
            try:
                process.wait(timeout=check["timeout"])
                result["status"] = "passed" if process.returncode == 0 else "failed"
            except subprocess.TimeoutExpired:
                result["status"] = "timeout"
                _terminate(process)
            except BaseException:
                _terminate(process)
                raise
            result["returncode"] = process.returncode
    except OSError as exc:
        result["stderr"] = f"Could not execute command: {exc}\n"
    finally:
        result["duration_seconds"] = round(time.perf_counter() - started, 6)
        for key, path in (("stdout", out_path), ("stderr", err_path)):
            if path.exists():
                result[key] += path.read_bytes().decode("utf-8", errors="replace")
                path.unlink()
    return result


def run(project=None, checks=None):
    root = discover_root(project)
    config = load_config(root)
    selected = list(dict.fromkeys(checks or []))
    unknown = set(selected) - config["checks"].keys()
    if unknown:
        raise ConfigError(f"Unknown checks: {', '.join(sorted(unknown))}")
    results = contained_path(root, ".harness/results")
    results.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    work = results / run_id
    work.mkdir()
    report = {"report_version": 1, "harness_version": __version__, "project": config["project"],
              "root": str(root), "run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat(),
              "selected": selected, "checks": {}}
    try:
        order = selected + [name for name in config["checks"] if name not in selected]
        for name in order:
            check = config["checks"][name]
            if check["state"] != "configured":
                result = {"status": check["state"], "reason": check["reason"], "returncode": None,
                          "stdout": "", "stderr": "", "duration_seconds": 0.0}
            elif name not in selected:
                result = {"status": "not_run", "reason": "Check was not selected", "returncode": None,
                          "stdout": "", "stderr": "", "duration_seconds": 0.0}
            else:
                result = _execute(root, check, work)
            result["selected"] = name in selected
            report["checks"][name] = result
    finally:
        work.rmdir()
    statuses = [report["checks"][name]["status"] for name in selected]
    code = 1 if any(s in ("failed", "timeout") for s in statuses) else (
        3 if not selected or "unconfigured" in statuses else 0)
    report["exit_code"] = code
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    path = results / f"{run_id}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [f"Harness {__version__} | {config['project']} | {run_id}", f"Selected: {', '.join(selected) or '(none)'}"]
    for name, item in report["checks"].items():
        lines.append(f"\n{name}: {item['status']} ({item['duration_seconds']:.6f}s) returncode={item['returncode']}")
        if "command" in item:
            lines.append(f"command={json.dumps(item['command'], ensure_ascii=False)} cwd={item['cwd']}")
        if item.get("reason"):
            lines.append(item["reason"])
        lines.extend(["stdout:", item["stdout"], "stderr:", item["stderr"]])
    lines.append(f"\nExit code: {code}")
    path.with_suffix(".log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report, code, path


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "update":
        # A running Windows console launcher can lock harness.exe while pip
        # replaces it. The module invocation keeps the executable unlocked.
        if os.name == "nt" and os.path.basename(sys.argv[0]).lower() == "harness.exe":
            print("Para atualizar, execute: python -m harness update", file=sys.stderr)
            return 2
        from harness.updater import main as update

        return update(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__, epilog="Atualizar o app: python -m harness update")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--project", help="Exact project root; otherwise discover upwards from cwd")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="append", help="Check name; repeat to select several")
    mode.add_argument("--all", action="store_true", help="Explicitly select every configured entry")
    mode.add_argument("--list", action="store_true", help="Inspect configuration without executing")
    mode.add_argument("--validate", action="store_true", help="Validate configuration without executing")
    args = parser.parse_args(argv)
    try:
        root = discover_root(args.project)
        config = load_config(root)
        if args.list or args.validate:
            print(json.dumps(config if args.list else {"valid": True, "root": str(root)}, ensure_ascii=False, indent=2))
            return 0
        report, code, path = run(root, list(config["checks"]) if args.all else args.check)
        for name, item in report["checks"].items():
            print(f"{name}: {item['status']}")
        print(f"Evidence: {path}")
        return code
    except (ConfigError, OSError) as exc:
        print(f"Harness error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
