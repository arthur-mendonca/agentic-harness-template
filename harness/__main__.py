"""Run the app without requiring its Scripts directory on PATH."""

from harness.runner import main


if __name__ == "__main__":
    raise SystemExit(main())
