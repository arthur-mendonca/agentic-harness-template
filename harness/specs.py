"""Read the deterministic Markdown contract of a full SDD task."""

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from harness.config import ConfigError
from harness.project_storage import local_path

SECTIONS = {
    "spec.md": ("Objetivo", "Escopo", "Comportamento esperado", "Requisitos", "Critérios de aceite", "Restrições e erros"),
    "plan.md": ("Componentes", "Estratégia e decisões", "Impactos", "Riscos e alternativas", "Verificações planejadas"),
    "tasks.md": ("Passos", "Verificação"),
}
KINDS = ("REQ", "AC", "T")
NUMBER = r"(?:[0-9]{3}|[1-9][0-9]{3,8})"
IDENTIFIER = re.compile(rf"(?P<kind>REQ|AC|T)-{NUMBER}")
HEADING = re.compile(r" {0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
FENCE = re.compile(r" {0,3}(\x60{3,}|~{3,})(.*)")
INLINE_CODE = re.compile(r"(\x60+)(.+?)\1")
MARKUP = re.compile(r"(\x60+).+?\1|<!--")
MARKER = r"(?:[-+*]|[0-9]{1,9}[.)])[ \t]+"
BULLET = r" {0,3}" + MARKER
CHECKBOX = r"\[(?P<done>[ xX])\][ \t]+"
STEP_DECLARATION = re.compile(rf"[ \t]*{MARKER}{CHECKBOX}T-{NUMBER}\b")
SPEC_DECLARATION = re.compile(rf"[ \t]*{MARKER}(?P<kind>REQ|AC)-{NUMBER}(?=:[ \t]*|[ \t]+\()")
INDENTED_DECLARATION = re.compile(rf"(?: {{4,}}|[ \t]*\t[ \t]*){MARKER}(?:{CHECKBOX})?(?:REQ|AC|T)-{NUMBER}\b")
SPEC_SECTION = {"REQ": "Requisitos", "AC": "Critérios de aceite"}
DESTINATION = r"(?:<([^>]+)>|((?:[^\s()\\]|\\[()]|\([^\s()]*\))+))"
LINK = re.compile(rf"\[[^]\r\n]+\]\(\s*{DESTINATION}(?:\s+\x22[^\x22]*\x22)?\s*\)")
LINK_DEFINITION = re.compile(rf" {{0,3}}\[(?P<label>[^]]+)\]:[ \t]*{DESTINATION}")
LINK_REFERENCE = re.compile(r"\[([^]\r\n]+)\]\[([^]\r\n]*)\]")


@dataclass(frozen=True)
class Diagnostic:
    file: str
    line: int
    code: str
    message: str

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Entry:
    id: str
    file: str
    line: int
    text: str
    refs: tuple[str, ...] = ()
    done: bool = False


def _visible_lines(text):
    fence = ""
    comment = False
    for number, line in enumerate(text.splitlines(), 1):
        if fence:
            marker = FENCE.fullmatch(line)
            if marker and marker[1].startswith(fence) and not marker[2].strip():
                fence = ""
            continue
        pieces = []
        while line:
            if comment:
                _, end, line = line.partition("-->")
                if not end:
                    break
                comment = False
            else:
                start = next((match for match in MARKUP.finditer(line) if match[0] == "<!--"), None)
                if start is None:
                    pieces.append(line)
                    break
                pieces.append(line[:start.start()])
                line = line[start.end():]
                comment = True
        line = "".join(pieces)
        marker = FENCE.fullmatch(line)
        if marker and (marker[1].startswith("~") or "\x60" not in marker[2]):
            fence = marker[1]
        else:
            yield number, line


def _slug(heading):
    return re.sub(r"[^\w -]", "", heading.casefold()).replace(" ", "-")


def _anchors(text):
    anchors = set()
    for _, line in _visible_lines(text):
        heading = HEADING.fullmatch(line)
        if heading:
            anchors.add(_slug(heading[2]))
        anchors.update(re.findall(r"\b(?:id|name)=[\x22']([^\x22']+)[\x22']", line))
    return anchors


class Document:
    def __init__(self, path, required, diagnostics):
        self.path = path
        self.diagnostics = diagnostics
        self.sections = {}
        self.lines = []
        if not path.is_file():
            self.issue(1, "missing_document", "Required Markdown file is missing")
            return
        try:
            self.lines = list(_visible_lines(path.read_text(encoding="utf-8-sig")))
        except UnicodeError:
            self.issue(1, "invalid_encoding", "Expected UTF-8 Markdown")
            return
        current = None
        name = None
        for number, line in self.lines:
            heading = HEADING.fullmatch(line)
            if heading and len(heading[1]) <= 2:
                current = None
                name = None
                if len(heading[1]) == 2:
                    name = heading[2]
                    if name in self.sections:
                        self.issue(number, "duplicate_section", f"Duplicate section: {name}")
                    else:
                        self.sections[name] = number, []
                        current = self.sections[name][1]
            elif current is not None:
                current.append((number, line))
            if self.path.name == "tasks.md" and name != "Passos" and STEP_DECLARATION.match(line):
                self.issue(number, "wrong_section", "Declare execution steps in Passos")
            if self.path.name == "spec.md" and (entry := SPEC_DECLARATION.match(line)):
                expected = SPEC_SECTION[entry["kind"]]
                if name != expected:
                    self.issue(number, "wrong_section", f"Declare {entry['kind']} entries in {expected}")
        for name in required:
            if name not in self.sections:
                self.issue(1, "missing_section", f"Missing section: {name}")

    def issue(self, line, code, message):
        self.diagnostics.append(Diagnostic(self.path.name, line, code, message))

    def prose(self, *sections):
        for name in sections:
            if name in self.sections:
                start, lines = self.sections[name]
                if not any(line.strip() and not HEADING.fullmatch(line) for _, line in lines):
                    self.issue(start, "empty_section", f"Provide content in {name}")

    def entries(self, section, kind, *, refs=False, checklist=False, required=True):
        if section not in self.sections:
            return []
        start, lines = self.sections[section]
        check = CHECKBOX if checklist else ""
        reference = r"[ \t]+\((?P<refs>[^)]*)\)" if refs else ""
        pattern = re.compile(rf"{BULLET}{check}(?P<id>{kind}-{NUMBER}){reference}:[ \t]*(?P<text>\S.*)")
        result = []
        for number, line in lines:
            if INDENTED_DECLARATION.match(line):
                self.issue(number, "indented_entry", "Declare contract entries as top-level lists")
                continue
            if not re.match(BULLET, line):
                continue
            item = pattern.fullmatch(line.rstrip())
            if not item:
                self.issue(number, "invalid_entry", f"Invalid {kind} entry in {section}")
                continue
            targets = tuple(value.strip() for value in item["refs"].split(",")) if refs else ()
            if refs and (any(not IDENTIFIER.fullmatch(value) for value in targets) or len(set(targets)) != len(targets)):
                self.issue(number, "invalid_references", f"Use distinct comma-separated identifiers in {item['id']}")
            result.append(Entry(item["id"], self.path.name, number, item["text"], targets,
                                checklist and item["done"].casefold() == "x"))
        if required and not result:
            self.issue(start, "missing_entry", f"Expected at least one {kind} entry in {section}")
        return result

    def links(self, root):
        definitions = {}
        for line_number, line in self.lines:
            definition = LINK_DEFINITION.match(line)
            if definition:
                definitions[_label(definition["label"])] = definition[2] or definition[3]
        for line_number, line in self.lines:
            spans = [part.span() for part in INLINE_CODE.finditer(line)]
            definition = LINK_DEFINITION.match(line)
            if definition:
                target = definition[2] or definition[3]
                if not _link_exists(root, self.path, target):
                    self.issue(line_number, "broken_link", f"Unresolved local link: {target}")
            for match in LINK.finditer(line):
                if _inside_code(match, spans) or _escaped(line, match.start()):
                    continue
                target = match[1] or match[2]
                if not _link_exists(root, self.path, target):
                    self.issue(line_number, "broken_link", f"Unresolved local link: {target}")
            for match in LINK_REFERENCE.finditer(line):
                if (not _inside_code(match, spans) and not _escaped(line, match.start())
                        and _label(match[2] or match[1]) not in definitions):
                    self.issue(line_number, "broken_link", f"Missing link definition: {match[2] or match[1]}")


def _label(text):
    return " ".join(text.split()).casefold()


def _inside_code(match, spans):
    return any(start <= match.start() and match.end() <= end for start, end in spans)


def _escaped(line, index):
    prefix = line[:index]
    return (index - len(prefix.rstrip("\\"))) % 2 == 1


def _link_exists(root, source, target):
    try:
        link = urlsplit(re.sub(r"\\([()])", r"\1", target))
        if link.scheme in ("http", "https", "mailto") or link.netloc and not link.scheme:
            return True
        relative = Path(unquote(link.path))
        if link.scheme or relative.anchor:
            return False
        absolute = Path(os.path.abspath(source.parent / relative)) if link.path else source
        path = local_path(root, absolute.relative_to(root).as_posix())
        if not path.exists():
            return False
        return (not link.fragment or path.suffix.lower() != ".md" or
                unquote(link.fragment) in _anchors(path.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        return False


def read_spec(path, root, diagnostics):
    spec = Document(path, SECTIONS["spec.md"], diagnostics)
    spec.prose("Objetivo", "Escopo", "Comportamento esperado", "Restrições e erros")
    spec.links(root)
    return (spec.entries("Requisitos", "REQ"), spec.entries("Critérios de aceite", "AC", refs=True))


def used_numbers(paths, kind):
    pattern = re.compile(rf"(?<![\w-]){kind}-(?P<number>{NUMBER})(?![\w-])")
    for path in paths:
        if path.is_file():
            for _, line in _visible_lines(path.read_text(encoding="utf-8-sig")):
                for match in pattern.finditer(line):
                    yield int(match["number"])
