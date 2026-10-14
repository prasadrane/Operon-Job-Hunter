#!/usr/bin/env python3
"""Fail if tracked files contain personal markers. Run before public push."""
import os
import re
import subprocess
import sys

# Generic secret shapes are checked in every run.
PATTERNS = [
    re.compile(r"TELEGRAM_CHAT_ID\s*=\s*\d+"),
    re.compile(r"(sk-[A-Za-z0-9]{16,}|AIza[A-Za-z0-9_-]{16,})"),
]

# Personal markers (name, phone, email, profile URL) live in an untracked file
# so this public script does not itself contain them. One regex per line;
# blank lines and lines starting with '#' are ignored.
LOCAL_PATTERNS_FILE = os.environ.get("GUARD_PERSONAL_PATTERNS_FILE", ".guard_personal_patterns")


def _load_local_patterns() -> list:
    if not os.path.exists(LOCAL_PATTERNS_FILE):
        return []
    out = []
    with open(LOCAL_PATTERNS_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(re.compile(line, re.I))
    return out


PATTERNS += _load_local_patterns()

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
