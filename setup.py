"""Project installer entry point and compatibility shim for setuptools builds."""

import sys


if __name__ == "__main__":
    build_commands = {"egg_info", "dist_info", "bdist_wheel", "editable_wheel", "sdist", "build", "build_py", "clean", "develop"}
    if len(sys.argv) > 1 and sys.argv[1] in build_commands:
        from setuptools import setup

        # Generated build/ files may be newer than source after a checkout.
        # Always package the current runtime rather than stale cached modules.
        setup(options={"build_py": {"force": True}})
    else:
        from harness.installer import main

        raise SystemExit(main())
