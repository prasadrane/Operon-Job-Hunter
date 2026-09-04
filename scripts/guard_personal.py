#!/usr/bin/env python3
"""Fail if tracked files contain personal markers. Run before public push."""
import os
import re
import subprocess
import sys

PATTERNS = [
    re.compile(r"\bPrasad\s+Rane\b", re.I),
    re.compile(r"linkedin\.com/in/rane-prasad", re.I),
    re.compile(r"\b513[-.\s]?967[-.\s]?9423\b"),
    re.compile(r"emailprasadrane@gmail\.com", re.I),
    re.compile(r"TELEGRAM_CHAT_ID\s*=\s*\d+"),
    re.compile(r"(sk-[A-Za-z0-9]{16,}|AIza[A-Za-z0-9_-]{16,})"),
]

ALLOWLIST_PATTERNS = {
    "scripts/guard_personal.py": [re.compile(r".*")],
}


def is_allowed(file_path: str, pat: re.Pattern) -> bool:
    norm = file_path.replace("\\", "/")
    for allowed_file, pats in ALLOWLIST_PATTERNS.items():
        if norm == allowed_file:
            for p in pats:
                if p.pattern == ".*" or p.pattern == pat.pattern:
                    return True
    return False


def main() -> int:
    try:
        files = subprocess.check_output(
            ["git", "ls-files"], text=True, encoding="utf-8"
        ).splitlines()
    except Exception as exc:
        print(f"Error executing git ls-files: {exc}", file=sys.stderr)
        return 1

    bad = []
    for f in files:
        if not os.path.exists(f):
            continue
        try:
            text = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for pat in PATTERNS:
            if pat.search(text) and not is_allowed(f, pat):
                bad.append((f, pat.pattern))

    if bad:
        for f, p in bad[:50]:
            print(f"PERSONAL MARKER {p!r} found in {f}")
        return 1

    print(f"guard_personal: clean ({len(files)} tracked files scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
