"""Validate links between specifications, planned checks and task steps."""

from collections import defaultdict

from harness.specs import Diagnostic, Document, SECTIONS, read_spec


def _issue(diagnostics, entry, code, message):
    diagnostics.append(Diagnostic(entry.file, entry.line, code, message))


def _index(entries, diagnostics):
    index = {}
    for entry in entries:
        if entry.id in index:
            _issue(diagnostics, entry, "duplicate_id", f"{entry.id} is already defined on line {index[entry.id].line}")
        else:
            index[entry.id] = entry
    return index


def _check_references(entries, references, diagnostics):
    matches = defaultdict(list)
    for entry in entries:
        if entry.id not in references:
            _issue(diagnostics, entry, "unknown_reference", f"Referenced identifier is missing: {entry.id}")
        else:
            matches[entry.id].append({"line": entry.line, "text": entry.text})
    return matches


def specification(root, path):
    diagnostics = []
    requirements, criteria = read_spec(path, root, diagnostics)
    requirements = _index(requirements, diagnostics)
    criteria = _index(criteria, diagnostics)
    by_requirement = defaultdict(list)
    for entry in criteria.values():
        for identifier in entry.refs:
            if identifier not in requirements:
                _issue(diagnostics, entry, "unknown_reference", f"Unknown requirement: {identifier}")
            else:
                by_requirement[identifier].append(entry.id)
    for entry in requirements.values():
        if not by_requirement[entry.id]:
            _issue(diagnostics, entry, "requirement_without_criterion", f"{entry.id} has no acceptance criterion")
    return requirements, criteria, by_requirement, diagnostics


def trace(root, paths):
    requirements, criteria, by_requirement, diagnostics = specification(root, paths["spec.md"])
    plan = Document(paths["plan.md"], SECTIONS["plan.md"], diagnostics)
    plan.prose("Componentes", "Estratégia e decisões", "Impactos", "Riscos e alternativas")
    plan.links(root)
    checks = _check_references(plan.entries("Verificações planejadas", "AC"), criteria, diagnostics)
    tasks = Document(paths["tasks.md"], SECTIONS["tasks.md"], diagnostics)
    tasks.links(root)
    steps = _index(tasks.entries("Passos", "T", refs=True, checklist=True), diagnostics)
    verifications = _check_references(tasks.entries("Verificação", "T", required=False), steps, diagnostics)
    by_criterion = defaultdict(list)
    for step in steps.values():
        wanted_requirements = {target for target in step.refs if target.startswith("REQ-")}
        wanted_criteria = {target for target in step.refs if target.startswith("AC-")}
        for target in step.refs:
            if target not in requirements and target not in criteria:
                _issue(diagnostics, step, "unknown_reference", f"Unknown requirement or criterion: {target}")
        if not wanted_requirements or not wanted_criteria:
            _issue(diagnostics, step, "unlinked_task", f"{step.id} needs requirements and acceptance criteria")
        linked = wanted_criteria & criteria.keys()
        parents = {parent for criterion in linked for parent in criteria[criterion].refs}
        if linked and parents != wanted_requirements:
            _issue(diagnostics, step, "task_requirement_mismatch", f"{step.id} must reference the requirements of its criteria")
        if step.done and not verifications[step.id]:
            _issue(diagnostics, step, "task_without_verification", f"{step.id} has no verification reference")
        for criterion in sorted(linked):
            by_criterion[criterion].append({
                "id": step.id, "line": step.line, "text": step.text, "done": step.done,
                "verifications": verifications[step.id],
            })
    for entry in criteria.values():
        if not checks[entry.id]:
            _issue(diagnostics, entry, "unverified_criterion", f"No planned verification for {entry.id}")
        if not by_criterion[entry.id]:
            _issue(diagnostics, entry, "unused_criterion", f"No execution step for {entry.id}")
    return {
        "valid": not diagnostics,
        "diagnostics": [diagnostic.to_dict() for diagnostic in diagnostics],
        "requirements": [{
            "id": requirement.id, "line": requirement.line, "text": requirement.text,
            "criteria": [{
                "id": identifier, "line": criteria[identifier].line, "text": criteria[identifier].text,
                "planned_verifications": checks[identifier], "tasks": by_criterion[identifier],
            } for identifier in by_requirement[requirement.id]],
        } for requirement in requirements.values()],
        "pending_tasks": [step.id for step in steps.values() if not step.done],
        "semantic_review": "agent_required",
    }
