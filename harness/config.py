"""Strict schema v1 validation without a runtime schema dependency."""

import json
import math
from pathlib import Path
import re


class ConfigError(ValueError):
    """The project configuration is unsafe, invalid, or incompatible."""


def contained_path(root, relative):
    """Resolve a project-local path, rejecting escapes through links as well."""
    root = Path(root).resolve()
    if not _text(relative) or Path(relative).is_absolute():
        raise ConfigError(f"Expected a relative project path: {relative!r}")
    try:
        resolved = (root / relative).resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        raise ConfigError(f"Invalid project path {relative!r}: {exc}") from exc
    if not resolved.is_relative_to(root):
        raise ConfigError(f"Path escapes the project: {relative!r}")
    return resolved


def discover_root(project=None):
    start = Path(project if project is not None else Path.cwd()).expanduser().resolve()
    if not start.is_dir():
        raise ConfigError(f"Project directory does not exist: {start}")
    candidates = [start] if project is not None else [start, *start.parents]
    for candidate in candidates:
        if any((candidate / name).is_file() for name in (".harness/harness.json", "harness.json")):
            return candidate
    raise ConfigError(f"No harness.json found from {start}")


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ConfigError(f"Duplicate JSON key: {key}")
        obj[key] = value
    return obj


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and "\x00" not in value


def validate_config(data, root):
    required = {"schema_version", "harness_version", "project", "checks"}
    if not isinstance(data, dict) or set(data) != required:
        raise ConfigError(f"Configuration must contain exactly: {sorted(required)}")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ConfigError("Unsupported schema_version; expected integer 1")
    if not _text(data["harness_version"]):
        raise ConfigError("harness_version must be nonempty text")
    if not _text(data["project"]) or not isinstance(data["checks"], dict):
        raise ConfigError("project must be nonempty text and checks must be an object")
    for name, check in data["checks"].items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            raise ConfigError(f"Invalid check name: {name!r}")
        if not isinstance(check, dict):
            raise ConfigError(f"Check {name} must be an object")
        state = check.get("state")
        if state == "configured":
            if set(check) != {"state", "command", "cwd", "timeout"}:
                raise ConfigError(f"Check {name}: configured requires command, cwd and timeout only")
            command = check["command"]
            if (not isinstance(command, list) or not command or not _text(command[0])
                    or not all(isinstance(arg, str) and "\x00" not in arg for arg in command)):
                raise ConfigError(f"Check {name}: command must be a nonempty list of text arguments")
            timeout = check["timeout"]
            if type(timeout) not in (int, float) or timeout <= 0 or timeout > 86400 or not math.isfinite(timeout):
                raise ConfigError(f"Check {name}: timeout must be finite, greater than zero and at most 86400 seconds")
            cwd = contained_path(root, check["cwd"])
            if not cwd.is_dir():
                raise ConfigError(f"Check {name}: cwd does not exist: {cwd}")
        elif state in ("not_applicable", "unconfigured"):
            if set(check) != {"state", "reason"} or not _text(check.get("reason")):
                raise ConfigError(f"Check {name}: {state} requires a reason and no command")
        else:
            raise ConfigError(f"Check {name}: unknown configuration state {state!r}")
    return data


def load_config(root):
    name = ".harness/harness.json" if (root / ".harness/harness.json").exists() else "harness.json"
    return validate_config(read_json(contained_path(root, name)), root)
