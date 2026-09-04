#!/usr/bin/env python3
"""Release gate: personal-data scan + tests + demo smoke. Exit non-zero on any fail."""
import subprocess
import sys


def run(cmd, **kw):
    print(f"\n$ {cmd}")
    return subprocess.call(cmd, shell=True, **kw)


def main() -> int:
    if run("python scripts/guard_personal.py") != 0:
        print("FAIL: personal markers present")
        return 1
    if run("python -m pytest tests/unit/ -q") != 0:
        print("FAIL: unit tests")
        return 1
    if run("python -m pytest tests/integration/ -q") != 0:
        print("FAIL: integration tests")
        return 1
    if run("python -m src.interface.cli.main demo --jobs 2 --fresh-db") != 0:
        print("FAIL: demo run")
        return 1
    print("\nRELEASE GATE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
