from pathlib import Path
import tempfile
import os
import unittest


def temporary_project():
    # Keep fixtures inside the workspace, including in restricted environments.
    parent = Path(__file__).resolve().parents[1] / ".harness" / "test-projects"
    parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=parent)


def directory_link(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            raise unittest.SkipTest(f"Directory links unavailable: {exc}") from exc
        # Junctions exercise Windows path escapes without Developer Mode/admin.
        import _winapi

        try:
            _winapi.CreateJunction(str(target), str(link))
        except OSError as junction_exc:
            raise unittest.SkipTest(f"Directory links unavailable: {junction_exc}") from junction_exc
