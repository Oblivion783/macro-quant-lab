"""Compliance gate for a public repo.

Run by the pre-commit hook on staged files and by CI on every tracked file:
    python -m mql.compliance                 # scan tracked files
    python -m mql.compliance file1 file2     # scan given files
Exit code 1 if anything is found. Private terms come from .compliance-local.txt (git-ignored) and
the COMPLIANCE_TERMS environment variable, and are never printed.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from . import config

LOCAL_FILE = ".compliance-local.txt"


def private_terms(root: Path) -> list[str]:
    terms = [t.strip() for t in os.environ.get("COMPLIANCE_TERMS", "").split(",") if t.strip()]
    p = root / LOCAL_FILE
    if p.exists():
        terms += [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return sorted(set(terms), key=str.lower)


def compile_rules(cfg: dict, private: list[str]) -> list[tuple[str, re.Pattern]]:
    rules = [(f"pattern '{p}'", re.compile(p, re.I)) for p in cfg.get("patterns", [])]
    rules += [(f"private term #{i + 1}", re.compile(r"\b" + re.escape(t) + r"\b", re.I)) for i, t in enumerate(private)]
    return rules


def scan_text(text: str, rules, allow: list[str]) -> list[tuple[int, str]]:
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        if any(a.lower() in low for a in allow):
            continue
        for label, rx in rules:
            if rx.search(line):
                hits.append((n, label))
    return hits


def tracked_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout
        return [root / f for f in out.splitlines()]
    except Exception:
        return [p for p in root.rglob("*") if p.is_file()]


def should_scan(path: Path, root: Path, cfg: dict) -> bool:
    rel = path.resolve().relative_to(root.resolve()).as_posix() if path.is_absolute() else path.as_posix()
    if any(rel == d or rel.startswith(d.rstrip("/") + "/") for d in cfg.get("skip_dirs", [])):
        return False
    if rel in ("config/compliance.yaml", "mql/compliance.py", "tests/test_compliance_podcast_brief.py"):
        return False
    return path.suffix.lower() in set(cfg.get("extensions", []))


def main(argv: list[str]) -> int:
    root = config.ROOT
    cfg = config.load_yaml("compliance.yaml")
    rules = compile_rules(cfg, private_terms(root))
    files = [Path(a) for a in argv] if argv else tracked_files(root)
    files = [f if f.is_absolute() else root / f for f in files]
    found = 0
    for f in files:
        if not f.exists() or not should_scan(f, root, cfg):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line, label in scan_text(text, rules, cfg.get("allow", [])):
            print(f"{f.relative_to(root)}:{line}: matches {label}")
            found += 1
    if found:
        print(f"\nCompliance gate: {found} match(es). Remove them, or add a genuinely harmless phrase to 'allow' in config/compliance.yaml.")
        return 1
    print(f"Compliance gate: clean ({len(rules)} rules).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
