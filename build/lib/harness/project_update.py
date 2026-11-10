"""Update local project controls, keeping backups and project-specific content."""

import json
from pathlib import Path
import re
import uuid

from harness import __version__
from harness.config import ConfigError, discover_root, load_config, read_json
from harness.installer import _preflight, init_project
from harness.project import PROJECT_FILES

START = "<!-- harness:managed:start -->"
END = "<!-- harness:managed:end -->"
STATE = ".harness/template-state.json"


def _custom_content(text, template):
    # Older installations had no ownership markers. Remove only exact known
    # boilerplate lines; keep additions, edited rules, headings and records.
    variants = [template, template.replace(".harness/", "")]
    known = {line.strip() for variant in variants for line in variant.splitlines() if line.strip()}
    known.add("- Registre os resultados reais em `planos/relatorios.md` e as pendências em `planos/pendencias.md`.")
    known.add("- Registre os resultados reais em `.harness/planos/relatorios.md` e as pendências em `.harness/planos/pendencias.md`.")
    old_consult = "- Consulte `.harness/planos/instrucoes.md` para as instruções e o planejamento da tarefa. Leia também `.harness/planos/IMPLEMENTATION_CONSTRAINTS.md`, quando existir."
    old_fallback = "- Em projetos ainda não migrados, consulte os documentos correspondentes em `planos/` e `memoria/` se os diretórios em `.harness/` não existirem."
    known.update((old_consult, old_consult.replace(".harness/", ""), old_fallback))
    known.add("- `memoria/` é versionável. Evidências detalhadas ficam em `.harness/results/`, ignorado pelo Git; comandos, resultados e limitações pertencem ao relatório final da sessão, sem cópia automática para Markdown permanente.")
    kept = []
    for section in re.split(r"(?m)(?=^#{1,6} )", text):
        lines = section.splitlines()
        heading = lines.pop(0) if lines and lines[0].startswith("#") else None
        custom = [line for line in lines if line.strip() not in known]
        if any(line.strip() for line in custom) or (heading and heading.strip() not in known):
            kept.extend(([heading] if heading else []) + custom + [""])
    return "\n".join(kept).strip()


def _updated_document(text, template, baseline=None):
    block = f"{START}\n<!-- harness:version {__version__} -->\n{template.rstrip()}\n{END}"
    if START in text or END in text:
        if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
            raise ConfigError("Invalid harness ownership markers; no project files were updated")
        start, end = text.index(START), text.index(END) + len(END)
        body = text[start + len(START):text.index(END)]
        body = re.sub(r"(?m)^<!-- harness:version [^\n]* -->\n?", "", body)
        custom = _custom_content(body, baseline if baseline is not None else template)
        return text[:start] + block + ("\n\n" + custom if custom else "") + text[end:]
    custom = _custom_content(text, template)
    return block + "\n" + ("\n" + custom + "\n" if custom else "")


def update_project(project):
    root = discover_root(project)
    config = load_config(root)
    directories = (".harness", ".harness/planos", ".harness/memoria", ".harness/backups")
    legacy = [name.removeprefix(".harness/") for name in PROJECT_FILES if name.startswith(".harness/")]
    _preflight(root, (*PROJECT_FILES, *legacy, STATE, ".harness/harness.json", "harness.json", ".gitignore"), directories)
    state_path = root / STATE
    baselines = read_json(state_path) if state_path.exists() else {}
    if not isinstance(baselines, dict) or any(not isinstance(value, str) for value in baselines.values()):
        raise ConfigError("Invalid harness template state; no project files were updated")
    planned, originals = {}, {}
    # Read and validate every document before creating backups or editing files.
    for name, template in PROJECT_FILES.items():
        path = root / name
        source = path
        if not source.exists() and name.startswith(".harness/"):
            source = root / name.removeprefix(".harness/")
        previous = source.read_bytes() if source.is_file() else b""
        updated = _updated_document(previous.decode("utf-8-sig"), template, baselines.get(name)).encode("utf-8")
        if not path.exists() or updated != previous:
            planned[name] = updated
            if source.is_file():
                originals[str(source.relative_to(root))] = previous
    config["harness_version"] = __version__
    config_name = ".harness/harness.json"
    config_path = root / config_name
    config_source = config_path if config_path.exists() else root / "harness.json"
    previous = config_source.read_bytes()
    updated = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if not config_path.exists() or previous != updated:
        planned[config_name] = updated
        originals[str(config_source.relative_to(root))] = previous
    updated_state = (json.dumps(PROJECT_FILES, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if not state_path.exists() or state_path.read_bytes() != updated_state:
        planned[STATE] = updated_state
        if state_path.exists():
            originals[STATE] = state_path.read_bytes()
    backup = root / ".harness/backups" / ("update-" + uuid.uuid4().hex) if originals else None
    if backup:
        for name, data in originals.items():
            target = backup / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    init_project(root)  # Preserve configured checks and maintain the ignore rule.
    for name, data in planned.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".update-" + uuid.uuid4().hex)
        try:
            temporary.write_bytes(data)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return {"root": str(root), "version": __version__, "updated": list(planned),
            "backup": str(backup) if backup else None, "checks_executed": False}
