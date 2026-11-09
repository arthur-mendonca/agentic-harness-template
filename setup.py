"""Project installer entry point and compatibility shim for setuptools builds."""

import sys


if __name__ == "__main__":
    build_commands = {"egg_info", "dist_info", "bdist_wheel", "sdist", "build", "build_py", "clean", "develop"}
    if len(sys.argv) > 1 and sys.argv[1] in build_commands:
        from setuptools import setup

        setup()
    else:
        from harness.installer import main

        raise SystemExit(main())
