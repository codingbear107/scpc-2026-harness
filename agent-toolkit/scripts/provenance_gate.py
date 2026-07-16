#!/usr/bin/env python3
"""Deterministic quality/provenance gate — stdlib only, exit 0 = clean, 1 = findings.

Generalized from a competition-harness compliance gate where it replaced a 19-agent LLM
audit with a 0-second deterministic check that caught the same defect classes on every
build. The core idea worth stealing is the PROVENANCE LEDGER: any "magic" literal that
drives behavior must be either derived from a declared source or CONSCIOUSLY allowlisted —
adding to the allowlist is a reviewable act, so nothing ships by accident.

Wire it three ways (all recommended together):
  - .git/hooks/pre-commit          -> blocks the commit (hard gate)
  - Claude Code Stop hook          -> report-only, every turn (early warning)
  - CI step                        -> blocks the merge

Adapt the CONFIG block per project. Run: python scripts/provenance_gate.py [--staged]
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ============================== CONFIG (adapt per project) ==============================

# Files/dirs to scan. Globs relative to repo root.
SCAN_GLOBS = ["src/**/*.py", "src/**/*.ts", "src/**/*.tsx", "app/**/*.py", "*.py"]
EXCLUDE_PARTS = {".git", "node_modules", "dist", "build", ".venv", "__pycache__", "tests"}

# 1) DENYLIST — patterns that must NEVER appear in shipped source. Zero legitimate uses.
DENYLIST: list[tuple[str, str]] = [
    (r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][A-Za-z0-9+/_\-]{16,}['\"]",
     "hardcoded credential-like literal"),
    (r"(?i)sk-[A-Za-z0-9]{20,}", "provider API key pattern"),
    (r"(?i)AKIA[0-9A-Z]{16}", "AWS access key pattern"),
    (r"console\.log\(", "debug logging left in shipped source"),
    (r"\bdebugger\b", "debugger statement"),
    (r"(?i)#\s*(hack|do not ship|remove before)", "explicit do-not-ship marker"),
    (r"(?i)localhost:\d{2,5}", "hardcoded local endpoint"),
    (r"(?i)\.only\(", "focused test (.only) left enabled"),
]

# 2) PROVENANCE LEDGER — behavior-driving literals must be allowlisted consciously.
#    LITERAL_PATTERN finds suspicious literals; ALLOWLIST is the reviewable ledger.
#    Every entry should carry a justification comment. An unexplained match FAILS the gate.
LITERAL_PATTERN = re.compile(
    r"['\"](https?://[^'\"]+|[0-9a-f]{24,}|[A-Z0-9_]{6,}@[a-z]+)['\"]"
)
ALLOWLIST: set[str] = {
    # "https://api.stripe.com/v1",   # payment provider base URL — public, stable
}

# 3) FORBIDDEN IMPORTS — packages that must not enter shipped source (env-specific).
FORBIDDEN_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+(pdb|ipdb|pytest(?=\s)|IPython)\b", re.MULTILINE
)

# 4) TRACKED-FILE POLICY — local-only artifacts that must never be committed.
NEVER_TRACKED = [".env", ".env.local", "*.pem", "*.key", "credentials.json"]

# ========================================================================================


def _files() -> list[Path]:
    out: list[Path] = []
    for g in SCAN_GLOBS:
        for p in ROOT.glob(g):
            if p.is_file() and not (set(p.parts) & EXCLUDE_PARTS):
                out.append(p)
    return sorted(set(out))


def run() -> list[str]:
    findings: list[str] = []
    for p in _files():
        rel = p.relative_to(ROOT)
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat, why in DENYLIST:
                if re.search(pat, line):
                    findings.append(f"[deny] {rel}:{lineno}: {why} -> {line.strip()[:70]}")
            for m in LITERAL_PATTERN.finditer(line):
                lit = m.group(1)
                if lit not in ALLOWLIST:
                    findings.append(
                        f"[provenance] {rel}:{lineno}: literal {lit[:50]!r} not in "
                        f"ALLOWLIST -> justify it there (with a comment) or move to config"
                    )
        for m in FORBIDDEN_IMPORT.finditer(text):
            findings.append(f"[import] {rel}: forbidden import {m.group(1)!r}")

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()
    for pattern in NEVER_TRACKED:
        rx = re.compile("^" + pattern.replace(".", r"\.").replace("*", ".*") + "$")
        for t in tracked:
            if rx.match(Path(t).name):
                findings.append(f"[tracked] {t} matches never-track pattern {pattern!r}")
    return findings


def main() -> int:
    findings = run()
    if not findings:
        print("provenance gate: clean")
        return 0
    print(f"provenance gate: {len(findings)} finding(s):")
    for f in findings[:50]:
        print("  - " + f)
    return 1


if __name__ == "__main__":
    sys.exit(main())
