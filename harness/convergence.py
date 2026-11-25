"""Link an agent's criterion assessments to a contract and recorded evidence."""

from hashlib import file_digest, sha256
import re

from harness.config import ConfigError, decode_json
from harness.project_storage import local_path
from harness.source_snapshot import capture, changes, validate_snapshot

STATES = ("met", "divergent", "unverified", "blocked")
REVIEW_STATES = ("passed", "findings", "not_performed", "blocked")
DEFAULT_REVIEW_POLICY = {"mode": "required", "reason": "Full tasks require independent review", "decided_by": "default"}


def validate_review_policy(policy):
    if (not _fields(policy, "mode", "reason", "decided_by") or policy["mode"] not in ("required", "optional")
            or not _text(policy["reason"]) or not _text(policy["decided_by"])):
        raise ConfigError("Review policy requires required/optional mode, reason and decided_by")
    return policy


def _review_provenance(root, review, contract, expected, hashes, source):
    if not _text(review.get("draft")):
        raise ConfigError("Passed review requires the exact explanation draft")
    provenance = review.get("provenance")
    if not _fields(provenance, "code", "explanation"):
        raise ConfigError("Passed review requires separate code and explanation provenance")
    draft_hash = sha256(review["draft"].encode("utf-8")).hexdigest()
    evidence = Evidence(root)
    for scope, entry in provenance.items():
        fields = {"reviewer", "scope", "contract", "revision", "artifact"}
        if scope == "code":
            fields.add("source_sha256")
        if scope == "explanation":
            fields.add("draft_sha256")
        if (not isinstance(entry, dict) or entry.keys() != fields
                or not all(_text(entry.get(key)) for key in ("reviewer", "scope", "revision", "artifact"))
                or entry["contract"] != contract):
            raise ConfigError(f"Invalid {scope} review provenance or contract")
        if scope == "code" and (source is None or entry["source_sha256"] != source["sha256"]):
            raise ConfigError("Code review source fingerprint no longer matches current source")
        if scope == "explanation" and entry["draft_sha256"] != draft_hash:
            raise ConfigError("Explanation draft changed since independent review")
        name, digest, _ = evidence.inspect({"file": entry["artifact"]})
        if expected is not None and expected.get(name) != digest:
            raise ConfigError(f"Review artifact changed since assessment: {name}")
        hashes[name] = digest


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
    if (status not in ("passed", "failed", "timeout", "interrupted", "unconfigured", "not_run", "not_applicable")
            or item.get("selected") is not (name in selected)):
        raise ConfigError(f"Check {name} has an invalid result in the report")
    if status in ("passed", "failed", "timeout", "interrupted") and name not in selected:
        raise ConfigError(f"Check {name} was not selected in the report")
    if status == "passed" and (type(item.get("returncode")) is not int or item["returncode"] != 0):
        raise ConfigError(f"Check {name} has an invalid passing return code")
    if status == "failed" and item.get("returncode") is None:
        return "failed_to_start"
    return status


class Evidence:
    def __init__(self, root, source=None):
        self.root = root
        self.source = source
        self.files = {}
        self.reports = {}

    def inspect(self, reference):
        if _fields(reference, "report", "check") and all(map(_text, reference.values())):
            name = reference["report"]
            if name not in self.reports:
                self.reports[name] = read_check_report(self.root, name)
            report, digest = self.reports[name]
            result = _check_result(report, reference["check"])
            if self.source is not None and result in ("passed", "failed", "timeout", "interrupted", "failed_to_start"):
                item = report["checks"][reference["check"]]
                try:
                    snapshot = validate_snapshot(item.get("source_snapshot"))
                except ConfigError:
                    result = "source_stale"
                else:
                    if (item.get("source_stable") is not True or item.get("source_snapshot_error")
                            or item.get("source_after_sha256") != snapshot["sha256"] or snapshot != self.source):
                        result = "source_stale"
        elif (isinstance(reference, dict) and {"file"} <= reference.keys()
              and reference.keys() <= {"file", "source_sha256", "limitation"} and _text(reference["file"])):
            name = reference["file"]
            if self.source is not None:
                if "source_sha256" in reference:
                    if reference["source_sha256"] != self.source["sha256"]:
                        raise ConfigError(f"Manual evidence source changed: {name}")
                elif not _text(reference.get("limitation")):
                    raise ConfigError("Manual evidence requires source_sha256 or an explicit limitation")
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
    blockers = {"timeout", "interrupted", "unconfigured", "failed_to_start"}
    if results & {"stale", "source_stale"}:
        status, reason = "unverified", "Refresh the changed, missing or source-incompatible evidence"
    elif status == "met" and "failed" in results:
        status, reason = "divergent", "A linked check failed"
    elif status == "met" or (status == "divergent" and not results & {"passed", "failed", "manual"}):
        if results & blockers:
            status, reason = "blocked", "A linked check timed out, was interrupted, could not start or lacks configuration"
        elif not results or results - {"passed", "manual"}:
            status, reason = "unverified", "Supply results of the linked verifications"
    return {"status": status, "reason": reason, "evidence": references}


def evaluate(root, trace, contract, assessment=None, *, recording=False, review_policy=None):
    """Return the current readiness and, when recording, its evidence hashes."""
    criteria = {entry["id"]: {"status": "unverified", "reason": "No current criterion assessment", "evidence": []}
                for requirement in trace["requirements"] for entry in requirement["criteria"]}
    review = {"status": "not_performed", "reason": "No current independent review recorded"}
    policy = validate_review_policy(DEFAULT_REVIEW_POLICY if review_policy is None else review_policy)
    source, source_error, source_changes = None, None, []
    try:
        source = capture(root)
    except ConfigError as exc:
        source_error = str(exc)
    hashes = {}
    valid = trace["valid"]
    awaiting = trace["spec_status"] == "awaiting_decision"
    if recording and (not valid or awaiting):
        raise ConfigError("The contract must be valid and clear of pending decisions; run sdd validate")
    if recording and (not _fields(assessment, "contract", "criteria", "review", "source_snapshot")):
        raise ConfigError("Assessment requires contract, criteria, review and source_snapshot from sdd verify")
    if recording and assessment["contract"] != contract:
        raise ConfigError("Contract changed; assess the revision shown by sdd verify")
    current = (valid and not awaiting and isinstance(assessment, dict) and not assessment.get("superseded")
               and assessment.get("contract") == contract)
    if current:
        try:
            recorded_source = validate_snapshot(assessment.get("source_snapshot"))
            if source is None:
                raise ConfigError(source_error or "Source scope could not be inspected")
            source_changes = changes(recorded_source, source)
            if recorded_source != source:
                raise ConfigError("Source changed since assessment: " + ", ".join(source_changes))
        except ConfigError as exc:
            if recording:
                raise
            source_error, current = str(exc), False
    if recording and source is None:
        raise ConfigError(source_error or "Source scope could not be inspected")
    if current:
        entries, review = assessment.get("criteria"), assessment.get("review")
        if not isinstance(entries, dict):
            raise ConfigError("Assessment criteria must be keyed by acceptance criterion ID")
        for identifier in entries.keys() - criteria.keys():
            raise ConfigError(f"Unknown acceptance criterion: {identifier}")
        if (not isinstance(review, dict) or not {"status", "reason"} <= review.keys()
                or review.keys() - {"status", "reason", "provenance", "draft"}
                or review["status"] not in REVIEW_STATES or not _text(review["reason"])):
            raise ConfigError(f"Review requires a reason and a status from: {', '.join(REVIEW_STATES)}")
        expected = None if recording else assessment.get("evidence_hashes")
        if not recording and not isinstance(expected, dict):
            raise ConfigError("Missing assessment evidence hashes")
        if review["status"] == "passed":
            try:
                _review_provenance(root, review, contract, expected, hashes, source)
            except (ConfigError, OSError) as exc:
                if recording:
                    raise
                review = {"status": "blocked", "reason": str(exc)}
        evidence = Evidence(root, source)
        for identifier, criterion in entries.items():
            if (not _fields(criterion, "status", "reason", "evidence") or criterion["status"] not in STATES
                    or not _text(criterion["reason"]) or not isinstance(criterion["evidence"], list)):
                raise ConfigError(f"{identifier} requires status, reason and an evidence list")
            if criterion["status"] == "divergent" and not criterion["evidence"]:
                raise ConfigError(f"{identifier} requires evidence of the divergence")
            criteria[identifier] = _assess(criterion, evidence, expected, hashes)
    if source is not None:
        try:
            after = capture(root)
            if after != source:
                source_changes = changes(source, after)
                raise ConfigError("Source changed during assessment: " + ", ".join(source_changes))
        except ConfigError as exc:
            if recording:
                raise
            source_error, current = str(exc), False
    unmet = [identifier for identifier, item in criteria.items() if item["status"] != "met"]
    return {
        "ready": bool(current and criteria and not unmet and not trace["pending_tasks"]
                      and (review["status"] == "passed" or
                           (policy["mode"] == "optional" and review["status"] == "not_performed"))),
        "assessment_current": current,
        "source_snapshot": source,
        "source_changes": source_changes,
        "source_error": source_error,
        "contract": contract,
        "spec_status": trace["spec_status"],
        "diagnostics": trace["diagnostics"],
        "pending_tasks": trace["pending_tasks"],
        "criteria": criteria,
        "unmet": unmet,
        "review": review,
        "review_policy": policy,
        "review_waived": bool(current and policy["mode"] == "optional" and review["status"] == "not_performed"),
        "independence_verification": "Reviewer identity and independence are declared; external evaluation is required",
        "semantic_review": trace["semantic_review"],
    }, hashes
