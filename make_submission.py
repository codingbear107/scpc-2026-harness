from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness import (
    FinalHarness,
    csv_round_trip,
    load_jsonl,
    run_harness,
    validate_payload,
    write_submission_csv,
)


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate DACON submission.csv for SCPC screening tasks.")
    parser.add_argument("--candidate", default="candidate_001", help="Harness/candidate name to store in meta.")
    parser.add_argument("--out", default="submission.csv", help="Output CSV path.")
    parser.add_argument("--json-out", default="", help="Optional debug JSON payload path.")
    args = parser.parse_args()

    tasks = load_jsonl(DATA_DIR / "screening_tasks.jsonl")
    payload = run_harness(tasks, FinalHarness, harness_name=args.candidate)
    expected_ids = {str(task["id"]) for task in tasks}
    validate_payload(payload, expected_ids)

    out_path = ROOT / args.out
    write_submission_csv(payload, out_path)
    restored = csv_round_trip(out_path)
    validate_payload(restored, expected_ids)

    if args.json_out:
        json_path = ROOT / args.json_out
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(
        {
            "status": "success",
            "csv": str(out_path),
            "answers": len(payload["answers"]),
            "meta": payload["meta"],
            "round_trip_ok": True,
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()

