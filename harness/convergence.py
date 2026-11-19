"""Link an agent's criterion assessments to a contract and recorded evidence."""

from hashlib import file_digest, sha256
import re

from harness.config import ConfigError, decode_json
from harness.project_storage import local_path

STATES = ("met", "divergent", "unverified", "blocked")
REVIEW_STATES = ("passed", "findings", "not_performed", "blocked")


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and "\0" not in value


def _fields(data, *fields):
    return isinstance(data, dict) and data.keys() == set(fields)


def read_check_report(root, name):
    if not re.fullmatch(r"[.]harness/results/[^/\\:]+[.]json", name):
        raise ConfigError(f"Expected a local check report in .harness/results: {name}")
    try:
        path = local_path(root, name)
        if not path.is_file():
            raise ConfigError(f"Expected a check report file: {name}")
        data = path.read_bytes()
        report = decode_json(data)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Cannot read check report {name}: {exc}") from exc
    if (not isinstance(report, dict) or type(report.get("report_version")) is not int
            or report["report_version"] != 1 or report.get("root") != str(root)):
        raise ConfigError(f"Invalid check report for this project: {name}")
    return report, sha256(data).hexdigest()


def manual_evidence_path(root, name):
    path = local_path(root, name).resolve()
    if not path.is_relative_to(root):
        raise ConfigError(f"Unsafe manual evidence path: {name}")
    if path.is_relative_to(root / ".harness/results"):
        suffix = path.suffix.casefold()
        runner_log = suffix == ".log" and (
            re.fullmatch(r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{8}", path.stem)
            or path.with_suffix(".json").exists()
        )
        if suffix == ".json" or runner_log:
            raise ConfigError("Use a check report reference with its check name for runner artifacts")
    if not path.is_file() or not path.stat().st_size:
        raise ConfigError(f"Manual verification file must exist and have content: {name}")
    return path


def _check_result(report, name):
    selected, checks = report.get("selected"), report.get("checks")
    item = checks.get(name) if isinstance(checks, dict) else None
    if not isinstance(selected, list) or not isinstance(item, dict):
        raise ConfigError(f"Check {name} is missing or invalid in the report")
    status = item.get("status")
    if (status not in ("passed", "failed", "timeout", "unconfigured", "not_run", "not_applicable")
            or item.get("selected") is not (name in selected)):
        raise ConfigError(f"Check {name} has an invalid result in the report")
    if status in ("passed", "failed", "timeout") and name not in selected:
        raise ConfigError(f"Check {name} was not selected in the report")
    if status == "passed" and (type(item.get("returncode")) is not int or item["returncode"] != 0):
        raise ConfigError(f"Check {name} has an invalid passing return code")
    if status == "failed" and item.get("returncode") is None:
        return "failed_to_start"
    return status


class Evidence:
    def __init__(self, root):
        self.root = root
        self.files = {}
        self.reports = {}

    def inspect(self, reference):
        if _fields(reference, "report", "check") and all(map(_text, reference.values())):
            name = reference["report"]
            if name not in self.reports:
                self.reports[name] = read_check_report(self.root, name)
            report, digest = self.reports[name]
            result = _check_result(report, reference["check"])
        elif _fields(reference, "file") and _text(reference["file"]):
            name = reference["file"]
            if name not in self.files:
                with manual_evidence_path(self.root, name).open("rb") as stream:
                    self.files[name] = file_digest(stream, "sha256").hexdigest()
            digest, result = self.files[name], "manual"
        else:
            raise ConfigError("Evidence requires either report and check, or a local manual verification file")
        return name, digest, result


def _assess(criterion, evidence, expected, hashes):
    references = []
    for reference in criterion["evidence"]:
        if not isinstance(reference, dict):
            raise ConfigError("Evidence references must be JSON objects")
        try:
            name, digest, result = evidence.inspect(reference)
            if expected is not None and expected.get(name) != digest:
                raise ConfigError(f"Evidence changed since the assessment: {name}")
            hashes[name] = digest
        except (ConfigError, OSError) as exc:
            if expected is None:
                raise
            references.append({**reference, "result": "stale", "reason": str(exc)})
        else:
            references.append({**reference, "result": result})
    results = {item["result"] for item in references}
    status = criterion["status"]
    reason = criterion["reason"]
    blockers = {"timeout", "unconfigured", "failed_to_start"}
    if "stale" in results:
        status, reason = "unverified", "Refresh the changed or missing evidence"
    elif status == "met" and "failed" in results:
        status, reason = "divergent", "A linked check failed"
    elif status == "met" or (status == "divergent" and not results & {"passed", "failed", "manual"}):
        if results & blockers:
            status, reason = "blocked", "A linked check timed out, could not start or lacks configuration"
        elif not results or results - {"passed", "manual"}:
            status, reason = "unverified", "Supply results of the linked verifications"
    return {"status": status, "reason": reason, "evidence": references}


def evaluate(root, trace, contract, assessment=None, *, recording=False):
    """Return the current readiness and, when recording, its evidence hashes."""
    criteria = {entry["id"]: {"status": "unverified", "reason": "No current criterion assessment", "evidence": []}
                for requirement in trace["requirements"] for entry in requirement["criteria"]}
    review = {"status": "not_performed", "reason": "No current independent review recorded"}
    hashes = {}
    valid = trace["valid"]
    awaiting = trace["spec_status"] == "awaiting_decision"
    if recording and (not valid or awaiting):
        raise ConfigError("The contract must be valid and clear of pending decisions; run sdd validate")
    if recording and (not _fields(assessment, "contract", "criteria", "review")):
        raise ConfigError("Assessment requires contract, criteria and review")
    if recording and assessment["contract"] != contract:
        raise ConfigError("Contract changed; assess the revision shown by sdd verify")
    current = (valid and not awaiting and isinstance(assessment, dict) and not assessment.get("superseded")
               and assessment.get("contract") == contract)
    if current:
        entries, review = assessment.get("criteria"), assessment.get("review")
        if not isinstance(entries, dict):
            raise ConfigError("Assessment criteria must be keyed by acceptance criterion ID")
        for identifier in entries.keys() - criteria.keys():
            raise ConfigError(f"Unknown acceptance criterion: {identifier}")
        if not _fields(review, "status", "reason") or review["status"] not in REVIEW_STATES or not _text(review["reason"]):
            raise ConfigError(f"Review requires a reason and a status from: {', '.join(REVIEW_STATES)}")
        expected = None if recording else assessment.get("evidence_hashes")
        if not recording and not isinstance(expected, dict):
            raise ConfigError("Missing assessment evidence hashes")
        evidence = Evidence(root)
        for identifier, criterion in entries.items():
            if (not _fields(criterion, "status", "reason", "evidence") or criterion["status"] not in STATES
                    or not _text(criterion["reason"]) or not isinstance(criterion["evidence"], list)):
                raise ConfigError(f"{identifier} requires status, reason and an evidence list")
            if criterion["status"] == "divergent" and not criterion["evidence"]:
                raise ConfigError(f"{identifier} requires evidence of the divergence")
            criteria[identifier] = _assess(criterion, evidence, expected, hashes)
    unmet = [identifier for identifier, item in criteria.items() if item["status"] != "met"]
    return {
        "ready": bool(current and criteria and not unmet and not trace["pending_tasks"]
                      and review["status"] in ("passed", "not_performed")),
        "assessment_current": current,
        "contract": contract,
        "spec_status": trace["spec_status"],
        "diagnostics": trace["diagnostics"],
        "pending_tasks": trace["pending_tasks"],
        "criteria": criteria,
        "unmet": unmet,
        "review": review,
        "semantic_review": trace["semantic_review"],
    }, hashes
