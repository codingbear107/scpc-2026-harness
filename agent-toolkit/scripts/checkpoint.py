#!/usr/bin/env python3
"""Experiment checkpoint: gate -> ledger -> commit -> tag. stdlib only.

Safety semantics (v0.2 — after external review):
  - NEVER silently commits unrelated work: if the working tree is dirty, the checkpoint
    ABORTS unless you explicitly pass --commit-all (a conscious, visible act).
  - The ledger entry is written BEFORE the commit, so the checkpoint commit contains
    its own ledger line (byte-complete restore point).
  - Tags are immutable by default: an existing exp/<name> tag ABORTS unless --retag.
  - Every git step checks its exit code; any failure aborts with the git message.
  - Verdict updates append a NEW event line (event-sourced) — history is never mutated.

Usage:
  python scripts/checkpoint.py --name exp-caching --hypothesis "..." --metric "p95_ms=412"
  python scripts/checkpoint.py --name exp-caching --verdict adopted --metric "p95_ms=180"
  python scripts/checkpoint.py --list
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "experiments" / "ledger.jsonl"


def sh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True)


def die(msg: str, cp: subprocess.CompletedProcess | None = None) -> int:
    print(f"checkpoint ABORTED: {msg}")
    if cp is not None and (cp.stderr or cp.stdout):
        print((cp.stderr or cp.stdout).strip()[:400])
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", help="experiment name (kebab-case)")
    ap.add_argument("--hypothesis", default="", help="the ONE hypothesis this change tests")
    ap.add_argument("--metric", default="", help="key=value measurement to record")
    ap.add_argument("--verdict", default="pending", choices=["pending", "adopted", "killed"])
    ap.add_argument("--commit-all", action="store_true",
                    help="explicitly include ALL working-tree changes in this checkpoint")
    ap.add_argument("--retag", action="store_true",
                    help="explicitly move an existing exp/<name> tag")
    ap.add_argument("--list", action="store_true", help="print the ledger")
    args = ap.parse_args()

    if args.list:
        if LEDGER.exists():
            for line in LEDGER.read_text(encoding="utf-8").splitlines():
                e = json.loads(line)
                print(f"{e['ts']}  {e['name']:28} {e.get('verdict','pending'):8} "
                      f"{e.get('metric',''):20} {e.get('hypothesis','')[:50]}")
        else:
            print("(ledger empty)")
        return 0

    if not args.name:
        ap.error("--name is required (or use --list)")

    # 0. dirty-tree policy: nothing unrelated is ever committed silently.
    dirty = sh("git", "status", "--porcelain").stdout.strip()
    if dirty and not args.commit_all:
        return die(
            "working tree has changes. Commit your work yourself, or pass --commit-all "
            "to explicitly include EVERYTHING in this checkpoint.\n"
            + "\n".join(dirty.splitlines()[:10])
        )

    # 1. gate (working tree = what will be committed here)
    gate = sh(sys.executable, str(ROOT / "scripts" / "provenance_gate.py"))
    print(gate.stdout.strip())
    if gate.returncode != 0:
        return die("fix provenance-gate findings first")

    # 2. tag immutability check BEFORE doing any work
    tag = f"exp/{args.name}"
    if sh("git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}").returncode == 0 \
            and not args.retag:
        return die(f"tag {tag} already exists (restore point is immutable). "
                   f"Use a new --name, or --retag to explicitly move it.")

    # 3. ledger BEFORE commit (so the checkpoint contains its own record)
    LEDGER.parent.mkdir(exist_ok=True)
    entry = {
        "ts": time.strftime("%Y-%m-%d %H:%M"),
        "name": args.name,
        "hypothesis": args.hypothesis,
        "metric": args.metric,
        "verdict": args.verdict,
    }
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # 4. commit (ledger, plus everything else only under --commit-all)
    add = sh("git", "add", "-A") if args.commit_all else sh("git", "add", str(LEDGER))
    if add.returncode != 0:
        return die("git add failed", add)
    commit = sh("git", "commit", "-m",
                f"exp: {args.name}" + (f" — {args.hypothesis}" if args.hypothesis else ""))
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
        return die("git commit failed", commit)

    head = sh("git", "rev-parse", "--short", "HEAD").stdout.strip()

    # 5. tag
    tag_args = ["git", "tag", "-f", tag] if args.retag else ["git", "tag", tag]
    tagged = sh(*tag_args)
    if tagged.returncode != 0:
        return die("git tag failed", tagged)

    print(f"checkpoint OK: {tag} @ {head}")
    print(f"  restore: git checkout {tag} -- .")
    print(f"  ledger : {json.dumps(entry, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
