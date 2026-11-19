"""Manage the local lifecycle and documents of an SDD task."""

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
import uuid

from harness.config import ConfigError, read_json
from harness.project_storage import PROJECT_LOCK, ProjectGit, atomic_write, local_path, project_lock
from harness.specs import KINDS, SECTIONS, used_numbers
from harness.traceability import specification, trace

TASKS = ".harness/tarefas"
BACKUPS = ".harness/backups/tasks"
SEQUENCE = ".harness/task-sequence.json"
TRANSITION = ".transition.json"
FOLDER = re.compile(r"([0-9]+)-[a-z0-9]+(?:-[a-z0-9]+)*")
UUID = re.compile(r"[0-9a-f]{32}")
HASH = re.compile(r"[0-9a-f]{64}")
STATES = {
    "open": "unverified",
    "in_progress": "unverified",
    "blocked": "impeded",
    "verified": "verified",
    "completed": "verified",
}
LITE_HEADINGS = ("Objetivo", "Critérios de aceite", "Passos", "Verificação")
DOCUMENTS = {
    "lite": {"tarefa.md": LITE_HEADINGS},
    "full": SECTIONS,
}
SPEC_STATES = ("draft", "awaiting_decision", "approved")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _digest(data):
    return sha256(data).hexdigest()


def _layout(meta):
    return meta["document_mode"] if meta["mode"] == "off" else meta["mode"]


def _render(title, headings, contents=None):
    sections = [f"# {title}"]
    for heading in headings:
        text = (contents or {}).get(heading, "").strip("\r\n")
        sections.append(f"## {heading}" + (f"\n\n{text}" if text else ""))
    return "\n\n".join(sections) + "\n"


def _make_documents(mode, title):
    return {name: _render(title, headings) for name, headings in DOCUMENTS[mode].items()}


def _lite_sections(title, source):
    headings = re.split(r"\n## ([^\r\n]+)\r?\n", source)
    contains_fence = re.search(r"(?m)^ {0,3}(?:\x60{3,}|~{3,})", source)
    if not contains_fence and tuple(headings[1::2]) == LITE_HEADINGS and headings[0].strip() == f"# {title}":
        return dict(zip(headings[1::2], headings[2::2]))
    return None


def _promotion(title, source):
    documents = _make_documents("full", title)
    contents = _lite_sections(title, source)
    if contents is not None:
        for name, sections in DOCUMENTS["full"].items():
            documents[name] = _render(title, sections, contents)
    elif source.strip():
        documents["spec.md"] += "\n## Contexto preservado da tarefa lite\n\n" + source
    return documents


def _archive_links(token):
    links = "\n".join(f"- [{name}](../../backups/tasks/{token}/{name})" for name in DOCUMENTS["full"])
    return f"\n## Documentos preservados da tarefa full\n\n{links}\n"


def _full_snapshot_valid(snapshot):
    return (isinstance(snapshot, dict) and isinstance(snapshot.get("token"), str)
            and UUID.fullmatch(snapshot["token"]) and isinstance(snapshot.get("files"), dict)
            and snapshot["files"].keys() == DOCUMENTS["full"].keys()
            and all(isinstance(digest, str) and HASH.fullmatch(digest) for digest in snapshot["files"].values()))


class TaskStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, name):
        return local_path(self.root, name)

    def _guard(self, git, *paths):
        if not git.active:
            return
        separator = git.key("/")
        protected = [git.key(name) for name in paths]
        for name, original in git.tracked.items():
            if any(name == target or name.startswith(target + separator) for target in protected):
                raise ConfigError(f"Task operation refuses to change tracked file: {original}")
        probes = {".harness/", *paths}
        rules = git.ignore_rules(probes)
        if any(not pattern or pattern.startswith(b"!") for _, pattern in rules.values()):
            raise ConfigError("Task files need local Git protection; run the project migration first")

    def _check_index(self, git):
        if git.active and git.index() != git.tracked:
            raise ConfigError("Git index changed during the task operation; retry")

    @contextmanager
    def _writer(self):
        git = ProjectGit(self.root)
        self._guard(git, PROJECT_LOCK)
        with project_lock(self.root):
            yield ProjectGit(self.root)

    def _folders(self):
        directory = self.path(TASKS)
        if not directory.exists():
            return []
        folders = []
        for child in directory.iterdir():
            match = FOLDER.fullmatch(child.name)
            if match and int(match[1]) > 0:
                folders.append((int(match[1]), child.name))
        return sorted(folders)

    def _task_path(self, folder, name):
        return self.path(f"{TASKS}/{folder}/{name}")

    def _read(self, folder):
        path = self._task_path(folder, "meta.json")
        return self._validate_meta(folder, read_json(path), path)

    def _validate_meta(self, folder, meta, path):
        if not isinstance(meta, dict):
            raise ConfigError(f"Invalid task metadata: {path}")
        identifier, number = meta.get("id"), meta.get("number")
        mode, status, layout = meta.get("mode"), meta.get("status"), meta.get("document_mode")
        if (not isinstance(identifier, str) or not UUID.fullmatch(identifier)
                or type(number) is not int or number != int(FOLDER.fullmatch(folder)[1])
                or mode not in ("lite", "full", "off") or (mode == "off" and layout not in ("lite", "full"))
                or not isinstance(status, str) or status not in STATES or meta.get("verification") != STATES[status]
                or not isinstance(meta.get("title"), str) or not isinstance(meta.get("mode_reason"), str)
                or not isinstance(meta.get("evidence"), list)
                or not all(isinstance(item, str) for item in meta["evidence"])
                or not isinstance(meta.get("manual_evidence", []), list)
                or not all(isinstance(item, str) for item in meta.get("manual_evidence", []))):
            raise ConfigError(f"Invalid task metadata: {path}")
        if "full_snapshot" in meta and (_layout(meta) != "lite" or not _full_snapshot_valid(meta["full_snapshot"])):
            raise ConfigError(f"Invalid previous full layout in task metadata: {path}")
        spec = meta.get("specification", {"state": "draft"})
        if (not isinstance(spec, dict) or spec.get("state") not in SPEC_STATES or
                (spec["state"] == "approved" and
                 (not isinstance(spec.get("sha256"), str) or not HASH.fullmatch(spec["sha256"])))):
            raise ConfigError(f"Invalid specification state in task metadata: {path}")
        counters = meta.get("document_ids", {})
        if (not isinstance(counters, dict) or counters.keys() - set(KINDS)
                or any(type(value) is not int or not 0 <= value < 10**9 for value in counters.values())):
            raise ConfigError(f"Invalid document identifier counters in task metadata: {path}")
        if "full_completion" in meta:
            hashes = meta["full_completion"]
            if (not isinstance(hashes, dict) or hashes.keys() != SECTIONS.keys()
                    or any(not isinstance(value, str) or not HASH.fullmatch(value) for value in hashes.values())):
                raise ConfigError(f"Invalid completion revision in task metadata: {path}")
        return meta

    def _result(self, folder, meta):
        result = {**meta, "path": f"{TASKS}/{folder}"}
        if _layout(meta) == "full":
            result["spec_status"] = self._spec_status(folder, meta)
            if meta["status"] == "completed" and not self._completion_current(folder, meta):
                result.update(status="verified", completion_stale=True)
        return result

    def _completion_current(self, folder, meta):
        if "full_completion" not in meta or self._spec_status(folder, meta) == "awaiting_decision":
            return False
        try:
            return meta["full_completion"] == self._contract_hashes(folder)
        except (ConfigError, OSError):
            return False

    def _spec_status(self, folder, meta):
        spec = meta.get("specification", {"state": "draft"})
        if spec["state"] != "approved":
            return spec["state"]
        try:
            digest = _digest(self._task_path(folder, "spec.md").read_bytes())
        except (ConfigError, OSError):
            return "awaiting_decision"
        return "approved" if digest == spec["sha256"] else "awaiting_decision"

    def _records(self):
        for _, folder in self._folders():
            try:
                path = self._task_path(folder, "meta.json")
                meta = self._read(folder) if path.is_file() else None
            except (ConfigError, OSError):
                meta = None
            yield folder, meta

    def _find(self, identifier):
        if re.fullmatch(r"[0-9]{1,18}", identifier):
            folders = [folder for number, folder in self._folders() if number == int(identifier)]
        elif UUID.fullmatch(identifier):
            folders = [folder for folder, meta in self._records() if meta is not None and meta["id"] == identifier]
        else:
            raise ConfigError("Use the short task number or the full task ID")
        if len(folders) != 1:
            raise ConfigError(f"Task ID not found or ambiguous: {identifier}")
        return folders[0], self._read(folders[0])

    def status(self, identifier):
        folder, meta = self._find(identifier)
        if self._task_path(folder, TRANSITION).exists():
            raise ConfigError(f"A mode transition is pending for {meta['number']:03d}; use sdd resume to recover it")
        return self._result(folder, meta)

    def list(self):
        results, unavailable = [], []
        for folder, meta in self._records():
            if meta is None:
                unavailable.append(f"{TASKS}/{folder}")
                continue
            result = self._result(folder, meta)
            try:
                if self._task_path(folder, TRANSITION).exists():
                    result["transition_pending"] = True
            except (ConfigError, OSError):
                result["transition_error"] = "Task transition could not be read"
            results.append(result)
        return {"tasks": results, "unavailable": unavailable}

    def new(self, title, mode, reason):
        title = title.strip()
        if not title or title.splitlines() != [title] or "\0" in title:
            raise ConfigError("Use a nonempty, single-line task title")
        folded = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
        slug = "-".join(re.findall(r"[a-z0-9]+", folded.lower()))[:64].rstrip("-") or "tarefa"
        with self._writer() as git:
            sequence = self.path(SEQUENCE)
            last = read_json(sequence) if sequence.exists() else 0
            if type(last) is not int or not 0 <= last < 10**18 - 1:
                raise ConfigError("Invalid task sequence")
            number = max(last, max((value for value, _ in self._folders()), default=0)) + 1
            if number >= 10**18:
                raise ConfigError("Task sequence exhausted")
            folder = f"{number:03d}-{slug}"
            location = self.path(f"{TASKS}/{folder}")
            documents = _make_documents(mode, title)
            self._guard(git, SEQUENCE, f"{TASKS}/{folder}",
                        *(f"{TASKS}/{folder}/{name}" for name in ("meta.json", *documents)))
            now = _now()
            meta = {"id": uuid.uuid4().hex, "number": number, "title": title, "mode": mode, "mode_reason": reason,
                    "status": "open", "verification": "unverified", "created_at": now, "updated_at": now, "evidence": []}
            if mode == "full":
                meta["specification"] = {"state": "draft"}
            directory = self.path(TASKS)
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=directory, prefix=".new-") as temporary:
                staging = Path(temporary)
                for name, text in documents.items():
                    atomic_write(staging / name, text.encode("utf-8"))
                atomic_write(staging / "meta.json", _json(meta))
                self._check_index(git)
                atomic_write(sequence, _json(number))
                if location.exists():
                    raise ConfigError(f"Task directory already exists: {folder}")
                staging.rename(location)
            return self._result(folder, meta)

    def resume(self, identifier):
        folder, meta = self._find(identifier)
        if not self._task_path(folder, TRANSITION).exists():
            return self._result(folder, meta)
        with self._writer() as git:
            folder, meta = self._for_write(identifier, git)
            return self._result(folder, meta)

    def _for_write(self, identifier, git):
        folder, meta = self._find(identifier)
        if self._task_path(folder, TRANSITION).exists():
            self._recover(folder, git)
            meta = self._read(folder)
        return folder, meta

    def _set_meta(self, folder, meta, git):
        self._guard(git, f"{TASKS}/{folder}/meta.json")
        self._check_index(git)
        meta["updated_at"] = _now()
        atomic_write(self._task_path(folder, "meta.json"), _json(meta))
        return self._result(folder, meta)

    def _require_full(self, meta):
        if meta["mode"] != "full":
            raise ConfigError("Specification contracts require full mode")

    def _contract(self, folder, meta):
        self._require_full(meta)
        paths = {name: self._task_path(folder, name) for name in SECTIONS}
        report = trace(self.root, paths)
        return {**report, "task_id": meta["id"], "path": f"{TASKS}/{folder}",
                "spec_status": self._spec_status(folder, meta)}

    def _contract_hashes(self, folder):
        paths = (self._task_path(folder, name) for name in SECTIONS)
        return {path.name: _digest(path.read_bytes()) if path.is_file() else None for path in paths}

    def contract(self, identifier):
        folder, meta = self._find(identifier)
        if self._task_path(folder, TRANSITION).exists():
            raise ConfigError("A mode transition is pending; use sdd resume before validating the contract")
        return self._contract(folder, meta)

    def allocate_id(self, identifier, kind):
        with self._writer() as git:
            folder, meta = self._for_write(identifier, git)
            self._require_full(meta)
            if kind not in KINDS:
                raise ConfigError(f"Invalid document identifier kind: {kind}")
            counters = meta.setdefault("document_ids", {})
            numbers = used_numbers((self._task_path(folder, name) for name in SECTIONS), kind)
            number = max(counters.get(kind, 0), max(numbers, default=0)) + 1
            if number >= 10**9:
                raise ConfigError(f"{kind} identifier counter is exhausted")
            counters[kind] = number
            self._set_meta(folder, meta, git)
            return {"task_id": meta["id"], "id": f"{kind}-{number:03d}"}

    def await_decision(self, identifier):
        with self._writer() as git:
            folder, meta = self._for_write(identifier, git)
            self._require_full(meta)
            if meta.get("specification") == {"state": "awaiting_decision"}:
                return self._result(folder, meta)
            meta["specification"] = {"state": "awaiting_decision"}
            return self._set_meta(folder, meta, git)

    def _approval_snapshot(self, folder, meta):
        self._require_full(meta)
        path = self._task_path(folder, "spec.md")
        digest = _digest(path.read_bytes())
        *_, diagnostics = specification(self.root, path)
        if diagnostics:
            first = diagnostics[0]
            raise ConfigError(f"{first.file}:{first.line}: {first.message}")
        if digest != _digest(path.read_bytes()):
            raise ConfigError("Specification changed while preparing approval; retry")
        return path, digest

    def approve(self, identifier):
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            raise ConfigError("Specification approval requires interactive confirmation from the user")
        folder, meta = self._find(identifier)
        if self._task_path(folder, TRANSITION).exists():
            raise ConfigError("A mode transition is pending; use sdd resume before approving")
        path, digest = self._approval_snapshot(folder, meta)
        print(f"Especificação {path}\nDigite o SHA-256 para confirmar a revisão {digest}", file=sys.stderr, flush=True)
        if sys.stdin.readline().strip() != digest:
            raise ConfigError("Specification confirmation did not match the displayed revision")
        with self._writer() as git:
            folder, current = self._for_write(identifier, git)
            _, latest = self._approval_snapshot(folder, current)
            if latest != digest or current["id"] != meta["id"]:
                raise ConfigError("Specification changed during confirmation; review the new revision")
            current["specification"] = {"state": "approved", "sha256": digest, "approved_at": _now()}
            return self._set_meta(folder, current, git)

    def _check_spec_progress(self, folder, meta, status):
        if status in ("in_progress", "verified", "completed") and (
                meta.get("specification", {}).get("state") == "awaiting_decision"
                or (meta["mode"] == "full" and self._spec_status(folder, meta) == "awaiting_decision")):
            raise ConfigError("Specification requires user approval before progressing")

    def _check_completion(self, folder, meta):
        before = self._contract_hashes(folder)
        report = self._contract(folder, meta)
        if not report["valid"]:
            first = report["diagnostics"][0]
            raise ConfigError(f"{first['file']}:{first['line']}: {first['message']}; run sdd validate")
        if report["pending_tasks"]:
            raise ConfigError(f"Unfinished execution steps: {', '.join(report['pending_tasks'])}")
        if None in before.values() or before != self._contract_hashes(folder):
            raise ConfigError("Contract changed during completion; validate the new revision")
        self._check_spec_progress(folder, meta, "completed")
        return before

    def set_status(self, identifier, status, evidence=(), manual_evidence=()):
        with self._writer() as git:
            folder, meta = self._for_write(identifier, git)
            if meta["mode"] == "off":
                raise ConfigError("Enable a managed mode before updating the task status")
            old_status = meta["status"]
            if status == "completed" and old_status not in ("verified", "completed"):
                raise ConfigError("Record a verified status before completing the task")
            self._check_spec_progress(folder, meta, status)
            supplied = evidence or manual_evidence
            references = list(dict.fromkeys(evidence)) if supplied else meta["evidence"]
            manual = list(dict.fromkeys(manual_evidence)) if supplied else meta.get("manual_evidence", [])
            passing = status in ("verified", "completed")
            if status == "verified" and old_status not in ("verified", "completed") and not supplied:
                raise ConfigError("Use --evidence or --manual-evidence to record a verification")
            if passing and not (references or manual):
                raise ConfigError("A verified task requires evidence")
            if references and (supplied or passing):
                self._check_evidence(references, passing=passing)
            if manual and (supplied or passing):
                self._check_manual_evidence(manual)
            if status == "completed" and meta["mode"] == "full":
                meta["full_completion"] = self._check_completion(folder, meta)
            else:
                meta.pop("full_completion", None)
            meta.update(status=status, verification=STATES[status], evidence=references)
            if manual:
                meta["manual_evidence"] = manual
            else:
                meta.pop("manual_evidence", None)
            return self._set_meta(folder, meta, git)

    def _check_evidence(self, paths, *, passing):
        for name in paths:
            if not re.fullmatch(r"[.]harness/results/[^/\\:]+[.]json", name):
                raise ConfigError(f"Expected a local check report in .harness/results: {name}")
            report = read_json(self.path(name))
            if not isinstance(report, dict) or report.get("report_version") != 1 or report.get("root") != str(self.root):
                raise ConfigError(f"Invalid check report for this project: {name}")
            selected, checks = report.get("selected"), report.get("checks")
            if passing and not self._report_passed(report, selected, checks):
                raise ConfigError(f"Selected checks must have passed in {name}")

    def _report_passed(self, report, selected, checks):
        if report.get("exit_code") != 0 or not isinstance(selected, list) or not isinstance(checks, dict):
            return False
        passed = False
        for check in selected:
            result = checks.get(check) if isinstance(check, str) else None
            if not isinstance(result, dict):
                return False
            if result.get("status") == "passed" and result.get("returncode") == 0:
                passed = True
            elif result.get("status") != "not_applicable":
                return False
        return passed

    def _check_manual_evidence(self, paths):
        for name in paths:
            path = self.path(name)
            if path.is_relative_to(self.root / ".harness/results") and path.suffix.casefold() == ".json":
                raise ConfigError("Use --evidence for JSON check reports")
            if not path.is_file() or not path.stat().st_size:
                raise ConfigError(f"Manual verification file must exist and have content: {name}")

    def change_mode(self, identifier, mode, reason):
        with self._writer() as git:
            folder, meta = self._for_write(identifier, git)
            layout = _layout(meta)
            if meta["mode"] == mode and meta["mode_reason"] == reason:
                return self._result(folder, meta)
            if layout == "full" and mode == "lite" and self._spec_status(folder, meta) == "awaiting_decision":
                raise ConfigError("Specification requires user approval before changing to lite")
            updated = {**meta, "mode": mode, "mode_reason": reason}
            if mode == "off":
                updated["document_mode"] = layout
            else:
                updated.pop("document_mode", None)
                if mode == "full":
                    updated.setdefault("specification", {"state": "draft"})
            if layout != mode and mode != "off" and "full" in (layout, mode):
                if meta["status"] == "completed" and (mode == "full" or not self._completion_current(folder, meta)):
                    updated["status"] = "verified"
                updated.pop("full_completion", None)
            if mode in ("off", layout):
                return self._set_meta(folder, updated, git)
            return self._change_layout(folder, meta, updated, git)

    def _change_layout(self, folder, source, updated, git):
        old_names = DOCUMENTS[_layout(source)]
        new_names = DOCUMENTS[updated["mode"]]
        token = uuid.uuid4().hex
        backup = f"{BACKUPS}/{token}"
        to_write = [f"{TASKS}/{folder}/{name}" for name in ("meta.json", *old_names, *new_names)]
        self._guard(git, f"{TASKS}/{folder}/{TRANSITION}", backup, *to_write)
        for name in new_names:
            if self._task_path(folder, name).exists():
                raise ConfigError(f"Refusing to overwrite an existing task file: {name}")
        original = {name: self._task_path(folder, name).read_bytes() for name in ("meta.json", *old_names)}
        if updated["mode"] == "full":
            lite = original["tarefa.md"].decode("utf-8-sig")
            snapshot = updated.pop("full_snapshot", None)
            payload = self._restore_full(source["title"], lite, snapshot) if snapshot else {
                name: text.encode("utf-8") for name, text in _promotion(source["title"], lite).items()
            }
        else:
            task = _render(source["title"], LITE_HEADINGS) + _archive_links(token)
            payload = {"tarefa.md": task.encode("utf-8")}
            updated["full_snapshot"] = {"token": token, "files": {name: _digest(original[name]) for name in old_names}}
        for name, data in original.items():
            path = self.path(f"{backup}/{name}")
            atomic_write(path, data)
            if path.read_bytes() != data:
                raise ConfigError(f"Could not verify backup of {name}")
        if "manual_evidence" in updated:
            archived = {self._task_path(folder, name): f"{backup}/{name}" for name in old_names}
            updated["manual_evidence"] = [archived.get(self.path(reference), reference)
                                          for reference in updated["manual_evidence"]]
        updated["updated_at"] = _now()
        transaction = {"token": token, "mode": updated["mode"], "result": _digest(_json(updated)),
                       "original": {name: _digest(data) for name, data in original.items()},
                       "generated": {name: _digest(data) for name, data in payload.items()}}
        journal = self._task_path(folder, TRANSITION)
        atomic_write(journal, _json(transaction))
        try:
            for name, data in payload.items():
                atomic_write(self._task_path(folder, name), data, exclusive=True)
            self._check_index(git)
            for name in old_names:
                if self._task_path(folder, name).read_bytes() != original[name]:
                    raise ConfigError(f"Task document changed during mode transition: {name}")
                self._task_path(folder, name).unlink()
            atomic_write(self._task_path(folder, "meta.json"), _json(updated))
        except (OSError, ValueError, KeyboardInterrupt):
            self._recover(folder, ProjectGit(self.root))
            raise
        journal.unlink()
        return {**self._result(folder, updated), "backup": backup}

    def _restore_full(self, title, lite, snapshot):
        token = snapshot["token"]
        payload = {name: self.path(f"{BACKUPS}/{token}/{name}").read_bytes() for name in DOCUMENTS["full"]}
        if {name: _digest(data) for name, data in payload.items()} != snapshot["files"]:
            raise ConfigError("Previous full task documents changed in the backup")
        content = lite.replace("\r\n", "\n").replace(_archive_links(token), "", 1)
        sections = _lite_sections(title, content)
        if sections is None:
            if content.strip():
                payload["spec.md"] += ("\n\n## Atualizações do modo lite\n\n" + content).encode("utf-8")
            return payload
        for name, headings in DOCUMENTS["full"].items():
            additions = [f"### {heading}\n\n{sections[heading].strip()}" for heading in headings
                         if heading in sections and sections[heading].strip()]
            if additions:
                payload[name] += ("\n\n## Atualizações do modo lite\n\n" + "\n\n".join(additions) + "\n").encode("utf-8")
        return payload

    def _recover(self, folder, git):
        journal = self._task_path(folder, TRANSITION)
        if not journal.exists():
            return
        transaction = read_json(journal)
        if not isinstance(transaction, dict):
            raise ConfigError("Invalid pending task transition")
        token, mode = (transaction.get(key) for key in ("token", "mode"))
        generated = transaction.get("generated")
        if (not isinstance(token, str) or not UUID.fullmatch(token) or mode not in ("lite", "full")
                or not isinstance(generated, dict) or generated.keys() != DOCUMENTS[mode].keys()):
            raise ConfigError("Invalid pending task transition")
        path = self._task_path(folder, "meta.json")
        previous = self.path(f"{BACKUPS}/{token}/meta.json")
        current = path.read_bytes()
        if _digest(current) == transaction.get("result"):
            old_names = DOCUMENTS["lite" if mode == "full" else "full"]
            if (any(self._task_path(folder, name).exists() for name in old_names)
                    or any(not self._task_path(folder, name).is_file() or
                           _digest(self._task_path(folder, name).read_bytes()) != digest
                           for name, digest in generated.items())):
                raise ConfigError("Task documents changed before the committed mode transition could be confirmed")
            self._guard(git, f"{TASKS}/{folder}/{TRANSITION}")
            journal.unlink()
            return
        if current != previous.read_bytes():
            raise ConfigError("Task metadata changed after an interrupted mode transition")
        original = self._validate_meta(folder, read_json(previous), previous)
        backups = {name: self.path(f"{BACKUPS}/{token}/{name}").read_bytes() for name in DOCUMENTS[_layout(original)]}
        hashes = {"meta.json": _digest(current), **{name: _digest(data) for name, data in backups.items()}}
        if hashes != transaction.get("original"):
            raise ConfigError("Task backup changed after an interrupted mode transition")
        self._guard(git, *(f"{TASKS}/{folder}/{name}" for name in (TRANSITION, *generated, *backups)))
        for name, data in backups.items():
            target = self._task_path(folder, name)
            if target.exists() and target.read_bytes() != data:
                raise ConfigError(f"Task document changed after an interrupted mode transition: {name}")
        for name, digest in generated.items():
            target = self._task_path(folder, name)
            if target.exists() and _digest(target.read_bytes()) != digest:
                raise ConfigError(f"New task document changed after an interrupted mode transition: {name}")
        for name, data in backups.items():
            target = self._task_path(folder, name)
            if not target.exists():
                atomic_write(target, data, exclusive=True)
        for name in generated:
            self._task_path(folder, name).unlink(missing_ok=True)
        journal.unlink()
