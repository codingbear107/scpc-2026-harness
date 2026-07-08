"""Build submission.csv and version it: snapshot the harness, commit, tag, and push.

Every CSV build is captured as an immutable git tag `candidate-NNN` on the current
branch, so any past version can be checked out and re-submitted later:

    git checkout candidate-013 && python make_submission.py   # rebuild that CSV

Usage:
    python build.py --name candidate_018 --note "short change description"
    python build.py                       # auto-numbers candidate_NNN
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from harness import (
    FinalHarness,
    csv_round_trip,
    load_json,
    load_jsonl,
    run_harness,
    validate_payload,
    write_submission_csv,
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"


def sh(*args: str, check: bool = True) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return (result.stdout or "").strip()


def next_candidate_name() -> str:
    tags = sh("git", "tag", "--list", "candidate-*", check=False).splitlines()
    nums = [int(t.rsplit("-", 1)[-1]) for t in tags if t.rsplit("-", 1)[-1].isdigit()]
    return f"candidate_{(max(nums) + 1 if nums else 18):03d}"


def dev_score() -> float:
    from run_dev import score_dev_submission  # local scorer

    tasks = load_jsonl(DATA / "dev_tasks.jsonl")
    payload = run_harness(tasks, FinalHarness, harness_name="build")
    ref = load_json(DATA / "dev_answers.json")
    return float(score_dev_submission(payload, ref)["overall"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build, version, commit, tag and push a submission.")
    parser.add_argument("--name", default="", help="Candidate name (auto if omitted).")
    parser.add_argument("--note", default="", help="Short change description for the commit/tag.")
    parser.add_argument("--no-push", action="store_true", help="Commit and tag locally without pushing.")
    args = parser.parse_args()

    name = args.name or next_candidate_name()
    tag = "candidate-" + name.split("_")[-1]

    # 1. Build the screening submission with a round-trip check.
    tasks = load_jsonl(DATA / "screening_tasks.jsonl")
    payload = run_harness(tasks, FinalHarness, harness_name=name)
    expected = {str(t["id"]) for t in tasks}
    validate_payload(payload, expected)
    out = ROOT / "submission.csv"
    write_submission_csv(payload, out)
    validate_payload(csv_round_trip(out), expected)

    # 2. Snapshot the exact code + payload for this version.
    cand_dir = REPORTS / name
    cand_dir.mkdir(parents=True, exist_ok=True)
    (cand_dir / "harness_snapshot.py").write_text((ROOT / "harness.py").read_text(encoding="utf-8"), encoding="utf-8")
    write_submission_csv(payload, cand_dir / "submission.csv")

    dev = dev_score()

    # 3. Commit the code and tag this build (CSV/reports are gitignored; the tagged
    #    harness.py fully regenerates the CSV).
    sh("git", "add", "harness.py", "run_dev.py", "make_submission.py", "build.py", "README.md")
    status = sh("git", "status", "--porcelain")
    # Keep commit/tag messages generic (a version marker + local dev score only). Any
    # design rationale belongs in a local note, never in the shared code/history.
    message = f"harness {name} (dev {dev:.4f})"
    if status:
        sh("git", "commit", "-q", "-m", message)
    else:
        sh("git", "commit", "-q", "--allow-empty", "-m", message)
    sh("git", "tag", "-f", tag, "-m", f"{name} (dev {dev:.4f})")

    branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    if not args.no_push:
        sh("git", "push", "-q", "origin", branch)
        sh("git", "push", "-q", "-f", "origin", tag)

    print(json.dumps(
        {
            "candidate": name,
            "tag": tag,
            "dev_overall": round(dev, 4),
            "answers": len(payload["answers"]),
            "round_trip_ok": True,
            "committed": True,
            "pushed": not args.no_push,
            "submission_csv": str(out),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
