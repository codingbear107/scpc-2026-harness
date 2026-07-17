#!/usr/bin/env python3
"""Deterministic quality/provenance gate — stdlib only. exit 0 = clean, 1 = findings.

Core idea (from a live-scored harness campaign): the PROVENANCE LEDGER — any behavior-
driving magic literal must be derived from a declared source or CONSCIOUSLY allowlisted,
so nothing ships by accident. Adding to ALLOWLIST is a reviewable act.

Modes:
  python scripts/provenance_gate.py                  # scan working tree (human output)
  python scripts/provenance_gate.py --staged         # scan STAGED contents (pre-commit)
  python scripts/provenance_gate.py --hook stop      # Claude Code Stop hook JSON
  python scripts/provenance_gate.py --hook posttool  # Claude Code PostToolUse hook JSON
                                                     #  (findings -> decision:block so the
                                                     #   agent SEES the reason and fixes it)

Matched secrets are REDACTED in all output (first 4 chars only).
Adapt the CONFIG block per project.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ============================== CONFIG (adapt per project) ==============================

CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".go", ".rb", ".java", ".cs"}
CONF_EXT = {".json", ".yml", ".yaml", ".toml", ".tf", ".sql", ".sh", ".ps1", ".env"}
DOC_EXT = {".md"}  # secrets pasted into docs are secrets too (DENYLIST only)
SCAN_EXT = CODE_EXT | CONF_EXT | DOC_EXT
SCAN_BASENAMES = {"Dockerfile", "docker-compose.yml", "Makefile"}
EXCLUDE_PARTS = {".git", "node_modules", "dist", "build", ".venv", "__pycache__",
                 "vendor", "coverage"}
EXCLUDE_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
                 "Cargo.lock"}
EXCLUDE_SUFFIXES = (".min.js", ".map")

# 1) DENYLIST — (pattern, why, extensions or None=all). Zero legitimate uses when it fires.
DENYLIST: list[tuple[str, str, set[str] | None]] = [
    (r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][A-Za-z0-9+/_\-]{16,}['\"]",
     "hardcoded credential-like literal", None),
    (r"(?i)\bsk-[A-Za-z0-9]{20,}", "provider API key pattern", None),
    (r"AKIA[0-9A-Z]{16}", "AWS access key pattern", None),
    (r"-----BEGIN (RSA |EC )?PRIVATE KEY-----", "private key material", None),
    (r"console\.log\(", "debug logging left in shipped source",
     {".js", ".ts", ".tsx", ".jsx", ".mjs"}),
    (r"\bdebugger\b", "debugger statement", {".js", ".ts", ".tsx", ".jsx", ".mjs"}),
    (r"(?i)#\s*(hack|do not ship|remove before)", "explicit do-not-ship marker", None),
    (r"(?i)\.only\(", "focused test (.only) left enabled",
     {".js", ".ts", ".tsx", ".jsx", ".mjs"}),
]

# 2) PROVENANCE LEDGER — behavior-driving literals must be consciously allowlisted.
#    v0.3 (alert-fatigue fix): by default only HIGH-ENTROPY literals in ASSIGNMENT context
#    are flagged. Quoted URLs in code are common and legitimate (fetch endpoints, configs),
#    so URL-ledger enforcement is OPT-IN via STRICT_LITERAL_LEDGER. Comment lines are
#    skipped for the ledger (doc links) — DENYLIST secret patterns still scan every line.
STRICT_LITERAL_LEDGER = False
ASSIGN_CTX = re.compile(r"[=:]\s*['\"]")
HIGH_ENTROPY_LIT = re.compile(r"['\"]([0-9a-fA-F]{24,}|[A-Za-z0-9+/]{40,}={0,2})['\"]")
URL_LIT = re.compile(r"['\"](https?://[^'\"\s]{8,})['\"]")
COMMENT_LEAD = re.compile(r"^\s*(#|//|\*|<!--)")
LITERAL_EXTS = CODE_EXT
ALLOWLIST: set[str] = {
    # "https://api.stripe.com/v1",   # payment provider base URL — public, stable
}

# 3) FORBIDDEN IMPORTS — must not enter shipped code (env/debug-only packages).
FORBIDDEN_IMPORT = re.compile(r"^\s*(?:import|from)\s+(pdb|ipdb|IPython)\b", re.MULTILINE)

# 4) NEVER-TRACKED — local-only artifacts that must never be committed.
NEVER_TRACKED = [".env", ".env.*", "*.pem", "*.key", "credentials.json"]

# ========================================================================================


def _redact(s: str) -> str:
    return s[:4] + "…(redacted)" if len(s) > 8 else "…(redacted)"


def _scannable(rel: str) -> bool:
    p = Path(rel)
    if p.name == "provenance_gate.py":  # the checker itself: its config IS compliance data
        return False
    if set(p.parts) & EXCLUDE_PARTS or p.name in EXCLUDE_NAMES:
        return False
    if any(p.name.endswith(sfx) for sfx in EXCLUDE_SUFFIXES):
        return False
    return p.suffix in SCAN_EXT or p.name in SCAN_BASENAMES


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def _sources(staged: bool) -> list[tuple[str, str]]:
    """[(relpath, content)] from staged index or working tree."""
    out: list[tuple[str, str]] = []
    if staged:
        names = _git("diff", "--cached", "--name-only", "--diff-filter=ACM").stdout.split("\n")
        for rel in filter(None, (n.strip() for n in names)):
            if not _scannable(rel):
                continue
            show = _git("show", f":{rel}")
            if show.returncode == 0:
                out.append((rel, show.stdout))
    else:
        for p in ROOT.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            if not _scannable(rel):
                continue
            try:
                out.append((rel, p.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                continue
    return out


def run(staged: bool = False) -> list[str]:
    findings: list[str] = []
    for rel, text in _sources(staged):
        ext = Path(rel).suffix
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat, why, exts in DENYLIST:
                if exts is not None and ext not in exts:
                    continue
                m = re.search(pat, line)
                if m:
                    findings.append(f"[deny] {rel}:{lineno}: {why} -> {_redact(m.group(0))}")
            if ext in LITERAL_EXTS and not COMMENT_LEAD.match(line) and ASSIGN_CTX.search(line):
                lits = [m.group(1) for m in HIGH_ENTROPY_LIT.finditer(line)]
                if STRICT_LITERAL_LEDGER:
                    lits += [m.group(1) for m in URL_LIT.finditer(line)]
                for lit in lits:
                    if lit not in ALLOWLIST:
                        findings.append(
                            f"[provenance] {rel}:{lineno}: literal {_redact(lit)!r} not in "
                            f"ALLOWLIST -> justify it there (with a comment) or move to config"
                        )
        if ext in CODE_EXT:
            for m in FORBIDDEN_IMPORT.finditer(text):
                findings.append(f"[import] {rel}: forbidden import {m.group(1)!r}")

    tracked = _git("ls-files").stdout.split()
    for pattern in NEVER_TRACKED:
        rx = re.compile("^" + pattern.replace(".", r"\.").replace("*", ".*") + "$")
        for t in tracked:
            if rx.match(Path(t).name):
                findings.append(f"[tracked] {t} matches never-track pattern {pattern!r}")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staged", action="store_true", help="scan staged contents (pre-commit)")
    ap.add_argument("--hook", choices=["stop", "posttool"], help="emit Claude Code hook JSON")
    args = ap.parse_args()

    findings = run(staged=args.staged)

    if args.hook == "stop":
        if findings:
            msg = f"[gate] {len(findings)} finding(s) — run: python scripts/provenance_gate.py"
            print(json.dumps({"systemMessage": msg}))
        return 0
    if args.hook == "posttool":
        if findings:
            reason = "provenance gate findings introduced/present:\n" + "\n".join(
                "- " + f for f in findings[:10])
            print(json.dumps({"decision": "block", "reason": reason}))
        return 0

    if not findings:
        print("provenance gate: clean" + (" (staged)" if args.staged else ""))
        return 0
    print(f"provenance gate: {len(findings)} finding(s)" + (" (staged)" if args.staged else "") + ":")
    for f in findings[:50]:
        print("  - " + f)
    return 1


if __name__ == "__main__":
    sys.exit(main())
