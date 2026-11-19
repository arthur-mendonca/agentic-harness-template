"""Filesystem and Git protection shared by project migration and task storage."""

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import subprocess
import tempfile

from harness.config import ConfigError

PROJECT_LOCK = ".harness/backups/.migration.lock"


def local_path(root, name):
    relative = Path(name)
    if relative.anchor or ".." in relative.parts:
        raise ConfigError(f"Unsafe migration path: {name}")
    path = root
    for index, part in enumerate(relative.parts):
        if Path(part).anchor or (os.name == "nt" and ":" in part):
            raise ConfigError(f"Unsafe project path component: {part}")
        path /= part
        try:
            mode = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode.st_mode) or getattr(mode, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ConfigError(f"Migration refuses links and junctions: {path}")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(mode.st_mode):
            raise ConfigError(f"Expected a migration directory: {path}")
    return path


class ProjectGit:
    def __init__(self, root):
        self.root = root
        self.active = any((parent / ".git").exists() for parent in (root, *root.parents))
        self.tracked = self.index() if self.active else {}

    def run(self, *args, codes=(0,), data=None):
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), *args], input=data, capture_output=True, timeout=15,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ConfigError(f"Cannot inspect Git protections: {exc}") from exc
        if result.returncode not in codes:
            raise ConfigError(f"Cannot inspect Git protections: {result.stderr.decode('utf-8', errors='replace').strip()}")
        return result.stdout

    @staticmethod
    def key(name):
        return os.path.normcase(name)

    def index(self):
        names = (os.fsdecode(name) for name in self.run("ls-files", "-z").split(b"\0") if name)
        return {self.key(name): name for name in names}

    def tracks(self, name):
        return self.key(name) in self.tracked

    def ignore_rules(self, paths):
        paths = sorted(paths)
        if not paths:
            return {}
        data = b"".join(os.fsencode(name) + b"\0" for name in paths)
        output = self.run("check-ignore", "--no-index", "-v", "-z", "--non-matching", "--stdin",
                          codes=(0, 1), data=data)
        fields = output.split(b"\0")[:-1]
        return {os.fsdecode(name): (source, pattern)
                for source, _, pattern, name in zip(fields[::4], fields[1::4], fields[2::4], fields[3::4])}

    def local_excludes(self, paths):
        rules = {}
        blocked = {}
        for name, (source, pattern) in self.ignore_rules(paths).items():
            if pattern.startswith(b"!") and source.endswith(b".gitignore"):
                blocked[name] = f"Project ignore rule exposes {name}"
            elif not pattern or pattern.startswith(b"!"):
                rules[name] = "/AGENTS.md" if name == "AGENTS.md" else "/.harness/"
        for name in blocked:
            group = "/AGENTS.md" if name == "AGENTS.md" else "/.harness/"
            rules = {path: rule for path, rule in rules.items() if rule != group}
        if not rules:
            return None, blocked
        exclude = Path(os.fsdecode(self.run("rev-parse", "--path-format=absolute", "--git-path", "info/exclude").rstrip(b"\r\n")))
        if exclude.is_relative_to(self.root):
            name = exclude.relative_to(self.root).as_posix()
        elif not self.tracks(".gitignore"):
            name = ".gitignore"
        else:
            blocked.update({path: f"Git exclusions for {path} require a change outside the project or in a tracked .gitignore"
                            for path in rules})
            return None, blocked
        return (name, sorted(set(rules.values()))), blocked


def atomic_write(path, data, *, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".migration-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.close()
            if exclusive:
                if os.name == "nt":
                    temporary.rename(path)
                else:
                    path.hardlink_to(temporary)
            else:
                if path.exists():
                    temporary.chmod(stat.S_IMODE(path.stat().st_mode))
                temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


@contextmanager
def project_lock(root):
    lock = local_path(root, PROJECT_LOCK)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as stream:
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ConfigError("Another operation is writing this project; retry") from exc
        yield
