"""Preview and migrate project controls and reviewed findings from legacy layouts."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
import uuid

from harness import __version__
from harness.config import SCHEMA_VERSION, ConfigError, discover_root, load_config, new_config, read_json, upgrade_config
from harness.installer import inspect_project
from harness.project import PROJECT_FILES
from harness.project_storage import ProjectGit as _Git, atomic_write as _atomic_write, local_path as _local_path, project_lock

STATE = ".harness/migration-state.json"
MIGRATION_VERSION = 1
TEMPLATE_STATE = ".harness/template-state.json"
CONFIG = ".harness/harness.json"
LOCAL_AGENTS = ".harness/AGENTS.md"
TASK_CONTEXT = ".harness/tarefas/000-contexto-legado/contexto.md"
DESTINATIONS = {
    "rule": ".harness/memoria/regras-negocio.md",
    "decision": ".harness/memoria/decisoes.md",
    "problem": ".harness/memoria/problemas-conhecidos.md",
    "pending": ".harness/pendencias.md",
    "task": TASK_CONTEXT,
}
OLD_REFERENCE = re.compile(
    r"(?<![\w/])(?:[.]/)?(?:(?:[.]harness/)?(?:planos/|tarefas/pendencias[.]md\b|relatorios[.]md\b)|memoria/)",
    re.IGNORECASE,
)
REPORTS = (".harness/relatorios.md", "relatorios.md", "planos/relatorios.md", ".harness/planos/relatorios.md")
OLD_FILES = (*REPORTS, "tarefas/pendencias.md", ".harness/tarefas/pendencias.md")
PROBLEMS = DESTINATIONS["problem"]


def _json_bytes(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _decode(name, data):
    try:
        return data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ConfigError(f"Invalid UTF-8 in {name}") from exc


def _digest(data):
    return sha256(data).hexdigest()


class _Migration:
    def __init__(self, root, render_document):
        self.root = root
        self.render = render_document
        self.git = _Git(root)
        self.originals = {}
        self.writes = {}
        self.archives = []
        self.blocked = []
        self.sources = {}
        self.protected = set()
        self.review_destinations = {}
        self.exclusion = None
        self.protection_blocked = False
        self.instructions_blocked = False
        self.archive_ineligible = {}

    def read(self, name):
        if name not in self.originals:
            self.originals[name] = _read_current(self.root, name)
        return self.originals[name]

    def directory(self, name):
        path = _local_path(self.root, name)
        if path.exists() and not path.is_dir():
            raise ConfigError(f"Expected a migration directory: {name}")
        return path

    def propose(self, name, data):
        original = self.read(name)
        if original != data and not self.git.tracks(name):
            self.writes[name] = data

    def documents(self, directory):
        path = self.directory(directory)
        if not path.exists():
            return
        for child in sorted(path.iterdir()):
            name = child.relative_to(self.root).as_posix()
            _local_path(self.root, name)
            if child.is_dir():
                yield from self.documents(name)
            elif child.suffix.lower() == ".md":
                yield name

    def plan_config(self, treated):
        old, canonical = self.read("harness.json"), self.read(CONFIG)
        if old is None and canonical is None:
            _, checks = inspect_project(self.root)
            config = new_config(self.root, checks)
        else:
            config = upgrade_config(load_config(self.root), self.root)
        if self.git.tracks(CONFIG) and (canonical is None or read_json(self.root / CONFIG)["schema_version"] != config["schema_version"]):
            self.blocked.append(f"Tracked {CONFIG} prevents the configuration layout upgrade")
        if old is not None and canonical is not None and treated.get("harness.json") != _digest(old):
            legacy = upgrade_config(read_json(self.root / "harness.json"), self.root)
            if "sdd" in legacy and "sdd" not in config:
                if self.git.tracks(CONFIG):
                    self.blocked.append(f"Tracked {CONFIG} cannot incorporate the legacy SDD policy")
                else:
                    config["sdd"] = legacy["sdd"]
            checks = dict(config["checks"])
            for name, check in legacy["checks"].items():
                if name in checks and checks[name] != check:
                    self.blocked.append(f"Conflicting check {name!r} in harness.json and {CONFIG}")
                elif name not in checks and self.git.tracks(CONFIG):
                    self.blocked.append(f"Tracked {CONFIG} cannot incorporate the legacy check {name!r}")
                else:
                    checks[name] = check
            config["checks"] = checks
        if old is not None and not self.blocked:
            treated["harness.json"] = _digest(old)
        self.propose(CONFIG, _json_bytes(config))

    def _combine_legacy_memory(self, name, text, template, baseline, treated):
        legacy_name = name.removeprefix(".harness/")
        data = self.read(legacy_name)
        if data is None or treated.get(legacy_name) == _digest(data):
            return text
        original = _decode(legacy_name, data)
        if name == PROBLEMS:
            original = _update_memory_reference(original, template)
        custom = _without_template(original, template, baseline, self.render).strip("\r\n")
        if not custom.strip() or custom.strip() in text:
            treated[legacy_name] = _digest(data)
        elif self.git.tracks(name):
            self.blocked.append(f"Tracked {name} cannot incorporate {legacy_name}")
        elif legacy_name in treated or _without_template(text, template, baseline, self.render).strip():
            self.sources[legacy_name] = data
        else:
            text = _append(text, custom)
            treated[legacy_name] = _digest(data)
        return text

    def plan_controls(self, treated):
        self.read("AGENTS.md")
        self.read(LOCAL_AGENTS)
        self.read(TEMPLATE_STATE)
        baselines = read_json(self.root / TEMPLATE_STATE) if self.originals[TEMPLATE_STATE] is not None else {}
        if not isinstance(baselines, dict) or any(not isinstance(value, str) for value in baselines.values()):
            raise ConfigError("Invalid harness template state")
        agents_name = LOCAL_AGENTS if self.git.tracks("AGENTS.md") else "AGENTS.md"
        templates = {agents_name: PROJECT_FILES["AGENTS.md"]}
        templates.update({name: template for name, template in PROJECT_FILES.items() if name != "AGENTS.md"})
        for name, template in templates.items():
            data = self.read(name)
            text = _decode(name, data) if data is not None else ""
            baseline = baselines.get(name)
            if name == PROBLEMS:
                known = template.replace(".harness/pendencias.md", ".harness/planos/pendencias.md")
                baseline = baseline or known
                text = _without_prefix(text, known)
                text = _update_memory_reference(text, template)
            if name != agents_name:
                for snapshot in (template, baseline):
                    if snapshot:
                        text = _without_prefix(text, snapshot)
            if name.startswith(".harness/memoria/"):
                text = self._combine_legacy_memory(name, text, template, baseline, treated)
            if self.git.tracks(name):
                if name == LOCAL_AGENTS and template.rstrip() not in text:
                    self.blocked.append(f"Tracked {name} cannot receive the local harness instructions")
                    self.instructions_blocked = True
                continue
            updated = self.render(text, template, baseline)
            if name == agents_name and OLD_REFERENCE.search(updated.replace("\\", "/")):
                self.sources[name] = self.read(name)
            else:
                self.propose(name, updated.encode("utf-8"))
        self.propose(TEMPLATE_STATE, _json_bytes(templates))
        return templates, agents_name

    def plan_legacy(self, treated):
        canonical_memory = {name.removeprefix(".harness/") for name in PROJECT_FILES if name.startswith(".harness/memoria/")}
        sources = set(OLD_FILES)
        for directory in ("planos", ".harness/planos", "memoria", ".harness/memoria"):
            sources.update(self.documents(directory))
        for name in sorted(sources):
            if name in canonical_memory or name in PROJECT_FILES:
                continue
            data = self.read(name)
            if data is not None and _digest(data) != treated.get(name):
                _decode(name, data)
                self.sources[name] = data

    def plan_archives(self):
        reports = sorted(name for name in self.sources if _report(name))
        agents = self.read("AGENTS.md")
        instructions = _decode("AGENTS.md", agents).replace("\\", "/") if agents and self.git.tracks("AGENTS.md") else ""
        for name in reports:
            if self.git.tracks(name):
                self.archive_ineligible[name] = f"Tracked report preserved: {name}"
            elif re.search(rf"(?<![\w/])(?:[.]/)?{re.escape(name)}(?![\w/])", instructions, re.IGNORECASE):
                self.archive_ineligible[name] = f"Tracked AGENTS.md still references {name}"
            elif not _writable(self.root, name):
                self.archive_ineligible[name] = f"Migration cannot archive read-only report: {name}"
        return [name for name in reports if name not in self.archive_ineligible]

    def add_findings(self, name, findings):
        complete = True
        for finding in findings:
            target = DESTINATIONS[finding["category"]]
            original = self.writes.get(target, self.read(target))
            text = _decode(target, original) if original is not None else "# Contexto de tarefas migrado\n"
            body = finding["text"].strip()
            if any(line.removeprefix("- ").split(" (origem ", 1)[0].strip() == body for line in text.splitlines()):
                continue
            if self.git.tracks(target):
                self.blocked.append(f"Tracked {target} cannot receive a finding from {name}")
                complete = False
            else:
                self.propose(target, _append(text, f"- {body} (origem {name}:{finding['line']})").encode("utf-8"))
        return complete

    def apply_review(self, review, treated, templates, agents_name):
        destinations = {*DESTINATIONS.values(), *(name.removeprefix(".harness/") for name in DESTINATIONS.values()
                                                   if name.startswith(".harness/memoria/"))}
        for name in sorted(destinations):
            data = self.read(name)
            self.review_destinations[name] = _digest(data) if data is not None else None
        review = _review_entries(review, self.sources, treated, agents_name, self.review_destinations)
        for name, entry in review.items():
            if name not in self.sources:
                continue
            if not self.add_findings(name, entry["findings"]):
                continue
            if name == agents_name:
                self.propose(name, self.render(entry["instructions"], templates[name]).encode("utf-8"))
            elif entry.get("archive"):
                if name in self.archive_ineligible:
                    self.blocked.append(self.archive_ineligible[name])
                    continue
                self.archives.append(name)
            treated[name] = _digest(self.sources[name])
        return sorted(set(self.sources) - set(review))

    def plan_git(self):
        if not self.git.active:
            return
        self.protected = {name for name in self.writes if name.startswith(".harness/") or name == "AGENTS.md"}
        self.protected.add(".harness/")
        if not self.git.tracks("AGENTS.md") and (self.read("AGENTS.md") is not None or "AGENTS.md" in self.writes):
            self.protected.add("AGENTS.md")
        exclusion, blocked = self.git.local_excludes(self.protected)
        self.blocked.extend(blocked.values())
        if any(name.startswith(".harness/") for name in blocked):
            self.protection_blocked = True
            self.writes.clear()
            self.archives.clear()
            return
        if "AGENTS.md" in blocked:
            self.writes.pop("AGENTS.md", None)
            self.protected.discard("AGENTS.md")
            self.instructions_blocked = True
        if exclusion:
            name, rules = exclusion
            previous = self.read(name) or b""
            suffix = "\n".join(rules).encode("utf-8") + b"\n"
            self.propose(name, previous + (b"\n" if previous and not previous.endswith(b"\n") else b"") + suffix)
            self.exclusion = name

    def summary(self, status, missing, archive_candidates, state_update):
        tracked = sorted(name for name in self.git.tracked.values()
                         if name.startswith(".harness/") or name in self.originals)
        return {
            "root": str(self.root), "version": __version__, "status": status,
            "inventory": {name: _digest(data) for name, data in self.originals.items() if data is not None},
            "destinations": self.review_destinations,
            "updated": list(self.writes),
            "create": [name for name in self.writes if self.originals[name] is None],
            "kept": sorted(name for name, data in self.originals.items()
                                                       if data is not None and name not in self.writes and name not in self.archives),
            "review_required": missing, "archive_after_review": archive_candidates,
            "archive": list(self.archives), "archived": [], "archive_ineligible": self.archive_ineligible,
            "tracked": tracked, "blocked": self.blocked, "backup": None, "state_update": state_update,
            "checks_executed": False,
        }


def _without_template(text, template, baseline, render):
    for snapshot in (template, baseline):
        if snapshot:
            remainder = _without_prefix(text, snapshot)
            if remainder != text:
                return remainder
    rendered = render(text, template, baseline)
    generated = render("", template)
    return rendered.removeprefix(generated) if rendered.startswith(generated) else text


def _without_prefix(text, snapshot):
    lines = text.splitlines(keepends=True)
    expected = snapshot.splitlines()
    if [line.rstrip("\r\n") for line in lines[:len(expected)]] == expected:
        return "".join(lines[len(expected):])
    return text


def _update_memory_reference(text, template):
    for line in template.splitlines():
        if ".harness/pendencias.md" in line:
            previous = line.replace(".harness/pendencias.md", ".harness/planos/pendencias.md")
            return re.sub(rf"(?m)^{re.escape(previous)}(?=\r?$)", lambda _: line, text)
    return text


def _append(text, block):
    return (text.rstrip("\r\n") + "\n\n" if text else "") + block + "\n"


def _report(name):
    return os.path.normcase(name) in map(os.path.normcase, REPORTS)


def _review_entries(review, sources, treated, agents_name, destinations):
    if review is None:
        return {}
    if not isinstance(review, dict) or set(review) != {"sources", "destinations"} or not isinstance(review["sources"], dict):
        raise ConfigError("Migration review requires sources and destination hashes")
    if set(sources).intersection(review["sources"]) and review["destinations"] != destinations:
        raise ConfigError("Migration destinations changed after review; inspect the new preview")
    for name, entry in review["sources"].items():
        if not isinstance(entry, dict):
            raise ConfigError(f"Invalid migration review entry: {name}")
        digest = entry.get("sha256")
        if name not in sources:
            if name in treated and digest == treated[name]:
                continue
            raise ConfigError(f"Unexpected or changed migration source: {name}")
        if digest != _digest(sources[name]):
            raise ConfigError(f"Migration source changed after review (hash mismatch): {name}")
        fields = {"sha256", "findings", "instructions"} if name == agents_name else {"sha256", "findings"}
        if _report(name):
            fields.add("archive")
            if type(entry.get("archive")) is not bool:
                raise ConfigError(f"Migration review must explicitly select whether to archive {name}")
        if set(entry) != fields or not isinstance(entry["findings"], list):
            raise ConfigError(f"Invalid migration review entry: {name}")
        if name == agents_name and (not isinstance(entry["instructions"], str)
                                    or OLD_REFERENCE.search(entry["instructions"].replace("\\", "/"))):
            raise ConfigError(f"Review must provide the custom instructions on canonical paths: {name}")
        lines = len(_decode(name, sources[name]).splitlines())
        for finding in entry["findings"]:
            if (not isinstance(finding, dict) or set(finding) != {"category", "text", "line"}
                    or not isinstance(finding["category"], str) or finding["category"] not in DESTINATIONS
                    or not isinstance(finding["text"], str) or not finding["text"].strip()
                    or finding["text"].splitlines() != [finding["text"]] or "\x00" in finding["text"]
                    or type(finding["line"]) is not int or not 1 <= finding["line"] <= lines):
                raise ConfigError(f"Invalid migration finding or line reference: {name}")
    return review["sources"]


def _load_state(plan):
    if plan.read(STATE) is None:
        return None, {}
    state = read_json(plan.root / STATE)
    if not isinstance(state, dict) or type(state.get("version")) is not int or not 0 <= state["version"] <= MIGRATION_VERSION:
        raise ConfigError("Invalid or unsupported migration state")
    if state["version"] < MIGRATION_VERSION:
        return None, {}
    if state.get("status", "complete") not in ("complete", "blocked"):
        raise ConfigError("Invalid migration status")
    sources = state.get("sources")
    for field in (sources, state.get("files", {})):
        if not isinstance(field, dict) or any(not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value)
                                              for value in field.values()):
            raise ConfigError("Invalid migration state hashes")
    return state, dict(sources)


def _writable(root, name):
    path = _local_path(root, name)
    parent = path.parent
    while not parent.exists():
        parent = parent.parent
    return os.access(parent, os.W_OK) and (not path.exists() or bool(path.stat().st_mode & stat.S_IWRITE))


def _preflight_writes(plan, names):
    for name in names:
        if not _writable(plan.root, name):
            raise ConfigError(f"Migration cannot write {name}")


def _read_current(root, name):
    path = _local_path(root, name)
    if path.exists() and not path.is_file():
        raise ConfigError(f"Expected a migration file: {name}")
    return path.read_bytes() if path.is_file() else None


def _assert_original(plan, name):
    if _read_current(plan.root, name) != plan.originals[name]:
        raise ConfigError(f"File changed during migration preview: {name}")


def _apply_locked(plan, state_data):
    if plan.git.active and plan.git.index() != plan.git.tracked:
        raise ConfigError("Git index changed during the migration preview; retry")
    for name in plan.originals:
        _assert_original(plan, name)
    backup = None
    originals = {name: data for name, data in plan.originals.items()
                 if data is not None and (name in plan.writes or name in plan.sources or name in plan.archives
                                          or name == STATE or (name == "harness.json" and CONFIG in plan.writes))}
    modified = {}
    ignores_verified = False
    try:
        if originals:
            backup = plan.directory(".harness/backups") / ("migration-" + uuid.uuid4().hex)
            for name, data in originals.items():
                saved = backup / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                with saved.open("xb") as stream:
                    stream.write(data)
                if saved.read_bytes() != data:
                    raise ConfigError(f"Migration backup verification failed for {name}")
        if plan.exclusion:
            name = plan.exclusion
            _assert_original(plan, name)
            _atomic_write(_local_path(plan.root, name), plan.writes[name])
            modified[name] = plan.writes[name]
        if any(not pattern or pattern.startswith(b"!") for _, pattern in plan.git.ignore_rules(plan.protected).values()):
            raise ConfigError("Git ignore verification failed for migration paths")
        ignores_verified = True
        plan.directory(".harness/results").mkdir(parents=True, exist_ok=True)
        for name, data in plan.writes.items():
            if name not in modified:
                _assert_original(plan, name)
                _atomic_write(_local_path(plan.root, name), data)
                modified[name] = data
        load_config(plan.root)
        if plan.git.active and plan.git.index() != plan.git.tracked:
            raise ConfigError("Git index changed during the migration; retry")
        if plan.archives:
            for name in plan.review_destinations:
                if _read_current(plan.root, name) != plan.writes.get(name, plan.originals[name]):
                    raise ConfigError(f"Migration destination changed before archiving: {name}")
        for name in plan.archives:
            _assert_original(plan, name)
            _local_path(plan.root, name).unlink()
            modified[name] = None
        if plan.archives and plan.git.active and plan.git.index() != plan.git.tracked:
            raise ConfigError("Git index changed while archiving; retry")
        if state_data is not None:
            _assert_original(plan, STATE)
            _atomic_write(_local_path(plan.root, STATE), state_data)
    except (OSError, ConfigError, KeyboardInterrupt) as exc:
        failures = []
        for name in reversed(modified):
            if name == plan.exclusion and ignores_verified and backup is not None:
                continue
            try:
                if _read_current(plan.root, name) != modified[name]:
                    raise ConfigError(f"{name} changed while applying the migration")
                path = _local_path(plan.root, name)
                previous = plan.originals[name]
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_write(path, previous)
            except (OSError, ConfigError):
                failures.append(name)
        if failures:
            raise ConfigError(f"Migration could not restore {', '.join(failures)}; backup: {backup}") from exc
        if not ignores_verified and backup is not None and backup.is_dir():
            try:
                shutil.rmtree(backup)
            except OSError as cleanup:
                raise ConfigError(f"Migration could not remove its incomplete backup: {backup}") from cleanup
        raise
    return backup


def _apply(plan, state_data):
    if not plan.writes and not plan.archives and state_data is None:
        return None
    with project_lock(plan.root):
        return _apply_locked(plan, state_data)


def migrate_project(project, render_document, *, dry_run=False, review=None):
    root = discover_root() if project is None else Path(project).expanduser().resolve()
    if not root.is_dir():
        raise ConfigError(f"Project directory does not exist: {root}")
    plan = _Migration(root, render_document)
    for directory in (".harness/backups", ".harness/results", ".harness/tarefas", "tarefas"):
        plan.directory(directory)
    state, treated = _load_state(plan)
    plan.plan_config(treated)
    templates, agents_name = plan.plan_controls(treated)
    plan.plan_legacy(treated)
    archive_candidates = plan.plan_archives()
    missing = plan.apply_review(review, treated, templates, agents_name)
    plan.plan_git()
    if plan.instructions_blocked:
        for name in (*plan.archives, agents_name):
            treated.pop(name, None)
        plan.archives.clear()
    status = "blocked" if plan.protection_blocked else "review_required" if missing else "blocked" if plan.blocked else "complete"
    state_data = None
    state_changed = state is None or state.get("status", "complete") != status or treated != state["sources"]
    if not missing and not plan.protection_blocked and (state_changed or plan.writes or plan.archives):
        if plan.git.tracks(STATE):
            plan.blocked.append(f"Tracked {STATE} cannot record the migration")
            plan.archives.clear()
            status = "blocked"
        else:
            files = state.get("files", {}) if state else {}
            state_data = _json_bytes({
                "version": MIGRATION_VERSION, "status": status, "updated_at": datetime.now(timezone.utc).isoformat(),
                "sources": treated,
                "files": {**files, **{name: _digest(data) for name, data in plan.writes.items()}},
            })
    _preflight_writes(plan, (*plan.writes, *plan.archives, *((STATE,) if state_data is not None else ())))
    result = plan.summary(status, missing, archive_candidates, state_update=state_data is not None)
    if dry_run or missing or plan.protection_blocked:
        return result
    backup = _apply(plan, state_data)
    result["backup"] = str(backup) if backup else None
    result["archived"] = plan.archives
    return result


def require_tasks_ready(root, config):
    message = "Prepare legacy project controls with python -m harness update --project . --dry-run"
    if config["schema_version"] != SCHEMA_VERSION or not _local_path(root, CONFIG).is_file():
        raise ConfigError(message)
    state_path = _local_path(root, STATE)
    if state_path.exists():
        state = read_json(state_path)
        if (isinstance(state, dict) and type(state.get("version")) is int and state["version"] == MIGRATION_VERSION
                and state.get("status", "complete") == "complete"):
            return
    else:
        legacy_paths = ("planos", "memoria", ".harness/planos", *OLD_FILES)
        agents = _local_path(root, "AGENTS.md")
        old_agents = agents.is_file() and OLD_REFERENCE.search(_decode("AGENTS.md", agents.read_bytes()).replace("\\", "/"))
        if not old_agents and not any(_local_path(root, name).exists() for name in legacy_paths):
            return
    raise ConfigError(message)
