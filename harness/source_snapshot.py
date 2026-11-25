"""Fingerprint the conservative project source scope without copying its contents."""

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from harness.config import ConfigError
from harness.project_storage import ProjectGit, local_path

VERSION = 1
SCOPE = "project-files-v1"
EXCLUDED_DIRECTORIES = frozenset({
    ".git", ".harness", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".nox", ".venv", "venv", "build", "dist", "target", "coverage",
})
HASH = re.compile(r"[0-9a-f]{64}")
INDEX_ENTRY = re.compile(r"(?:100644|100755|120000|160000):[0-9a-f]{40}(?:[0-9a-f]{24})?")
CONFIG = ".harness/harness.json"
MAX_FILES = 100000


def excluded(name, *, directory=False):
    parts = Path(name).parts
    # Git worktree metadata may itself be a file. Other generated names only
    # exclude directories; extensionless source scripts may share those names.
    return (any(part in (".git", ".harness") for part in parts)
            or any(part in EXCLUDED_DIRECTORIES or part.endswith(".egg-info")
                   for part in (parts if directory else parts[:-1])))


def _relative(name):
    return (isinstance(name, str) and name and "\\" not in name and "\0" not in name
            and not Path(name).anchor and name == Path(name).as_posix()
            and all(part not in (".", "..") and ":" not in part for part in name.split("/"))
            and (name == CONFIG or not excluded(name)))


def _digest(snapshot):
    data = {key: snapshot[key] for key in ("version", "scope", "files", "index")}
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")).hexdigest()


def validate_snapshot(snapshot):
    if (not isinstance(snapshot, dict) or snapshot.keys() != {"version", "scope", "files", "index", "sha256"}
            or type(snapshot["version"]) is not int or snapshot["version"] != VERSION or snapshot["scope"] != SCOPE
            or not isinstance(snapshot["files"], dict) or not isinstance(snapshot["index"], dict)
            or len(snapshot["files"]) > MAX_FILES or len(snapshot["index"]) > MAX_FILES):
        raise ConfigError("Invalid or unsupported source snapshot scope")
    for key, pattern in (("files", HASH), ("index", INDEX_ENTRY)):
        if any(not _relative(name) or not isinstance(value, str) or not pattern.fullmatch(value)
               for name, value in snapshot[key].items()):
            raise ConfigError("Unsafe or invalid source snapshot manifest")
    if snapshot["sha256"] != _digest(snapshot):
        raise ConfigError("Source snapshot digest does not match its manifest")
    return snapshot


def changes(before, after):
    validate_snapshot(before)
    validate_snapshot(after)
    return sorted({name for key in ("files", "index") for name in before[key].keys() | after[key].keys()
                   if before[key].get(name) != after[key].get(name)})


def _inventory(root):
    names = []

    def visit(directory):
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                name = path.relative_to(root).as_posix()
                mode = entry.stat(follow_symlinks=False)
                if excluded(name, directory=stat.S_ISDIR(mode.st_mode)):
                    continue
                if stat.S_ISLNK(mode.st_mode) or getattr(mode, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise ConfigError(f"Source scope contains a link or junction: {name}")
                if stat.S_ISDIR(mode.st_mode):
                    visit(path)
                elif stat.S_ISREG(mode.st_mode):
                    names.append(name)
                    if len(names) > MAX_FILES:
                        raise ConfigError("Source scope exceeds the safe file limit")
                else:
                    raise ConfigError(f"Source scope contains a special file: {name}")

    visit(root)
    if (root / CONFIG).exists():
        local_path(root, CONFIG)
        names.append(CONFIG)
    return sorted(names)


def _index(root, git):
    result = {}
    if git.active:
        for entry in git.run("ls-files", "--stage", "-z").split(b"\0"):
            if not entry:
                continue
            metadata, raw = entry.split(b"\t", 1)
            mode, digest, stage = metadata.split()
            name = os.fsdecode(raw).replace(os.sep, "/")
            if excluded(name) and name != CONFIG:
                continue
            if stage != b"0" or mode == b"160000":
                raise ConfigError(f"Source scope has an unresolved index entry or submodule: {name}")
            if not _relative(name):
                raise ConfigError(f"Unsafe source index path: {name}")
            result[name] = (mode + b":" + digest).decode("ascii")
    return result


def capture(root):
    root = Path(root).resolve()
    try:
        git = ProjectGit(root)
        names, index = _inventory(root), _index(root, git)
        files = {}
        stamps = {}
        for name in names:
            path = local_path(root, name)
            before = path.stat()
            digest = sha256()
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            after = path.stat()
            stamp = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode)
            if stamp(before) != stamp(after):
                raise ConfigError(f"Source changed while reading: {name}")
            files[name], stamps[name] = digest.hexdigest(), stamp(after)
        if names != _inventory(root) or index != _index(root, git):
            raise ConfigError("Source inventory or Git index changed during snapshot")
        for name, expected in stamps.items():
            if stamp(local_path(root, name).stat()) != expected:
                raise ConfigError(f"Source changed during snapshot: {name}")
    except OSError as exc:
        raise ConfigError(f"Cannot inspect source scope: {exc}") from exc
    snapshot = {"version": VERSION, "scope": SCOPE, "files": files, "index": index}
    snapshot["sha256"] = _digest(snapshot)
    return validate_snapshot(snapshot)
