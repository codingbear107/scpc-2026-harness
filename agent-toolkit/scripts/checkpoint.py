#!/usr/bin/env python3
"""Experiment checkpoint: gate -> snapshot -> tag -> ledger. stdlib only.

Generalized from a competition pipeline that versioned 30+ candidates; every experiment
was one-command restorable and two live regressions were rolled back losslessly because
of it. Use for ANY measurable experiment (see the experiment-discipline skill).

Usage:
  python scripts/checkpoint.py --name exp-caching-orders \
      --hypothesis "read-through cache removes N+1 on /orders" \
      --metric "p95_ms=412"            # measurement BEFORE or AFTER, your call
  python scripts/checkpoint.py --list

What it does:
  1. Runs provenance_gate.py — findings ABORT the checkpoint (nothing dirty gets tagged).
  2. Commits the working tree (if dirty) with the experiment name.
  3. Tags HEAD as `exp/<name>` (one-command restore: `git checkout exp/<name> -- .`).
  4. Appends one JSON line to experiments/ledger.jsonl:
     {name, hypothesis, metric, commit, ts} — adopted AND killed experiments both stay
     in the ledger; failures are data that kill future dead ends.
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", help="experiment name (kebab-case)")
    ap.add_argument("--hypothesis", default="", help="the ONE hypothesis this change tests")
    ap.add_argument("--metric", default="", help="key=value measurement to record")
    ap.add_argument("--verdict", default="", help="adopted|killed|pending (default pending)")
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

    # 1. gate
    gate = sh(sys.executable, "scripts/provenance_gate.py")
    print(gate.stdout.strip())
    if gate.returncode != 0:
        print("checkpoint ABORTED: fix gate findings first")
        return 1

    # 2. commit if dirty
    if sh("git", "status", "--porcelain").stdout.strip():
        sh("git", "add", "-A")
        c = sh("git", "commit", "-m", f"exp: {args.name}"
               + (f" — {args.hypothesis}" if args.hypothesis else ""))
        print(c.stdout.strip().splitlines()[0] if c.stdout else "committed")

    commit = sh("git", "rev-parse", "--short", "HEAD").stdout.strip()

    # 3. tag (idempotent: -f allows re-checkpointing the same experiment)
    sh("git", "tag", "-f", f"exp/{args.name}")
    print(f"tagged exp/{args.name} @ {commit}  (restore: git checkout exp/{args.name} -- .)")

    # 4. ledger
    LEDGER.parent.mkdir(exist_ok=True)
    entry = {
        "ts": time.strftime("%Y-%m-%d %H:%M"),
        "name": args.name,
        "hypothesis": args.hypothesis,
        "metric": args.metric,
        "verdict": args.verdict or "pending",
        "commit": commit,
    }
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print("ledger +1:", json.dumps(entry, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
