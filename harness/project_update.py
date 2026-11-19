"""Render managed project controls and expose the project update entry point."""

import re

from harness import __version__
from harness.config import ConfigError
from harness.migration import TEMPLATE_STATE as STATE, migrate_project

START = "<!-- harness:managed:start -->"
END = "<!-- harness:managed:end -->"
CONTROL_LINE = re.compile(
    r"(?:\A|(?<=[\r\n])) {0,3}(?:"
    rf"({re.escape(START)}|{re.escape(END)})[ \t]*|"
    r"(`{3,}|~{3,})([^\r\n]*))(?=[\r\n]|\Z)"
)
VERSION_HEADER = re.compile(r"\A(?:\r\n?|\n)(?:<!-- harness:version [^\r\n]* -->(?:\r\n?|\n))?")


def _ownership_markers(text):
    markers = []
    fence = ""
    for line in CONTROL_LINE.finditer(text):
        marker, delimiter, info = line.groups()
        if marker:
            if not fence:
                markers.append(line)
        elif not fence:
            if delimiter[0] == "~" or "`" not in info:
                fence = delimiter
        elif delimiter.startswith(fence) and not info.strip():
            fence = ""
    return markers


def _matches_template(text, template):
    return text.splitlines() == template.rstrip("\r\n").splitlines()


def _updated_document(text, template, baseline=None):
    block = f"{START}\n<!-- harness:version {__version__} -->\n{template.rstrip()}\n{END}"
    markers = _ownership_markers(text)
    if markers:
        if [marker.group(1) for marker in markers] != [START, END]:
            raise ConfigError("Invalid harness ownership markers; no project files were updated")
        start, end = markers
        body = text[start.end():end.start()]
        body = VERSION_HEADER.sub("", body)
        if _matches_template(body, template) or (baseline is not None and _matches_template(body, baseline)):
            body = ""
        return text[:start.start()] + block + ("\n\n" + body if body else "") + text[end.end():]
    if not text or _matches_template(text, template):
        return block + "\n"
    return block + "\n\n" + text


def update_project(project, *, dry_run=False, review=None):
    return migrate_project(project, _updated_document, dry_run=dry_run, review=review)
