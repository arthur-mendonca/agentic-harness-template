"""Atualize o app com um único comando, usando o mesmo Python da instalação."""

import argparse
from importlib import metadata
import json
from pathlib import Path
import site
import re
import subprocess
import sys
import tomllib
from urllib.parse import urlsplit
from urllib.request import url2pathname


PACKAGE = "agentic-verifiable-harness"
REPOSITORY = "git+https://github.com/arthur-mendonca/agentic-harness-template.git"


class UpdateError(Exception):
    """An update stopped without completing installation."""


def _source(path):
    manifest = path / "pyproject.toml"
    if not manifest.is_file():
        return False
    data = tomllib.loads(manifest.read_text(encoding="utf-8-sig"))
    return data.get("project", {}).get("name") == PACKAGE


def _installation():
    """Return source, editable mode and user scope for the running app."""
    root = Path(__file__).resolve().parent.parent
    try:
        dist = metadata.distribution(PACKAGE)
    except metadata.PackageNotFoundError:
        dist = None
    # A source checkout can expose egg-info before the actual editable install.
    # Prefer the installed metadata so a --user installation keeps its scope.
    if dist is not None and Path(dist.locate_file("")).resolve() == root:
        dist = next((candidate for candidate in metadata.distributions()
                     if candidate.metadata["Name"] == PACKAGE
                     and Path(candidate.locate_file("")).resolve() != root), dist)
    user = bool(dist and site.USER_SITE and sys.prefix == sys.base_prefix
                and Path(dist.locate_file("")).resolve().is_relative_to(Path(site.USER_SITE).resolve()))
    if _source(root):
        return root, True, user
    if dist is None:
        raise UpdateError("Esta cópia não tem uma instalação Python identificável. Instale o pacote antes de atualizar.")
    direct = json.loads(dist.read_text("direct_url.json") or "{}")
    url = direct.get("url", "")
    if urlsplit(url).scheme == "file" and "dir_info" in direct:
        parsed = urlsplit(url)
        path = Path(url2pathname(("//" + parsed.netloc if parsed.netloc else "") + parsed.path)).resolve()
        if _source(path):
            return path, bool(direct["dir_info"].get("editable")), user
    # Wheels have no live source tree. VCS installations retain their repository,
    # while dropping a previous pin so update can retrieve the current revision.
    if direct.get("vcs_info", {}).get("vcs") == "git":
        revision = direct["vcs_info"].get("requested_revision", "")
        if revision and not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", revision):
            url += "@" + revision
        return "git+" + url, False, user
    return None, False, user


def _run(command):
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise UpdateError(f"Comando necessário não encontrado: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        step = "Git (alterações locais foram preservadas)" if command[0] == "git" else "pip"
        raise UpdateError(f"{step} falhou (código {exc.returncode}). A atualização não foi concluída.") from exc


def update_app():
    source, editable, user = _installation()
    print(f"Atualizando o app com {sys.executable}", flush=True)
    if isinstance(source, Path):
        if not (source / ".git").exists():
            raise UpdateError(f"A fonte local não é um checkout Git: {source}")
        # Git refuses overwrites/conflicts and divergent histories. Never reset,
        # stash, clean, or select the caller's current project as the app source.
        _run(["git", "-C", str(source), "pull", "--ff-only"])
    command = [sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall"]
    if user:
        command.append("--user")
    if editable:
        command.append("--editable")
    command.append(str(source) if source is not None else REPOSITORY)
    _run(command)
    print("Atualização do app concluída.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m harness update", description=__doc__)
    parser.add_argument("--project", metavar="CAMINHO", help="Atualizar AGENTS.md e controles locais, sem reinstalar o app")
    args = parser.parse_args(argv)
    try:
        if args.project is not None:
            from harness.project_update import update_project

            result = update_project(args.project)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print("Atualização dos controles do projeto concluída.")
        else:
            update_app()
        return 0
    except (UpdateError, OSError, ValueError) as exc:
        print(f"Erro na atualização: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
