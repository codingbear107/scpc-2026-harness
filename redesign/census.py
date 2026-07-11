"""Clean-room step 1: dev-only sentence census.

Extracts every sentence from the 120 dev tasks' prompt / visible_history / personal_memory
(object attrs bodies are deliberately NOT a directive source), normalizes instance slots
(codes, markers, times, dates, numbers, person names) to placeholders, and prints the
deduplicated template inventory plus the trailing corrective-clause inventory.

Design inputs: data/dev_tasks.jsonl + data/dev_answers.json only.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

WM = re.compile(r"WM-\d+")
MARKER = re.compile(r"marker_[a-z]+")
MASK = re.compile(r"masked_ref")
TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
DATE = re.compile(r"\b\d{2}-\d{2}\b")
NUM = re.compile(r"\b\d+\b")
LATIN = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=다\.)|(?<=요\.)|(?<=함\.)|(?<=음\.)")


def load_tasks() -> list[dict]:
    return [json.loads(l) for l in (DATA / "dev_tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def person_names(tasks: list[dict]) -> set[str]:
    names: set[str] = set()
    for t in tasks:
        for rec in (t.get("device_state", {}).get("records") or []):
            v = rec.get("value")
            if isinstance(v, dict) and v.get("person"):
                names.add(str(v["person"]))
    return names


def normalize(sent: str, names: set[str]) -> str:
    s = WM.sub("<WM>", sent)
    s = MARKER.sub("<MK>", s)
    s = MASK.sub("<MASK>", s)
    s = TIME.sub("<TIME>", s)
    s = DATE.sub("<DATE>", s)
    for n in names:
        s = s.replace(n, "<PERSON>")
    s = NUM.sub("<N>", s)
    return s.strip()


def sentences_of(task: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for seg in SENT_SPLIT.split(str(task.get("prompt") or "")):
        if seg.strip():
            out.append(("prompt", seg.strip()))
    for h in task.get("visible_history") or []:
        text = str(h.get("summary") if isinstance(h, dict) else h)
        for seg in SENT_SPLIT.split(text):
            if seg.strip():
                out.append(("history", seg.strip()))
    for m in task.get("personal_memory") or []:
        text = str(m.get("text") if isinstance(m, dict) else m)
        for seg in SENT_SPLIT.split(text):
            if seg.strip():
                out.append(("memory", seg.strip()))
    return out


def main() -> int:
    tasks = load_tasks()
    names = person_names(tasks)
    answers = json.loads((DATA / "dev_answers.json").read_text(encoding="utf-8"))["answers"]

    templates: Counter[tuple[str, str]] = Counter()
    corrective: defaultdict[str, list[str]] = defaultdict(list)  # normalized clause -> [control]
    by_template_tasks: defaultdict[tuple[str, str], set[str]] = defaultdict(set)

    for t in tasks:
        tid = str(t.get("id"))
        control = answers.get(tid, {}).get("control", "?")
        for source, sent in sentences_of(t):
            norm = normalize(sent, names)
            templates[(source, norm)] += 1
            by_template_tasks[(source, norm)].add(tid)
            if source == "prompt" and sent.lstrip().startswith(("단,", "다만")):
                corrective[norm].append(control)

    print(f"tasks={len(tasks)}  sentence instances={sum(templates.values())}  unique templates={len(templates)}")
    for src in ("prompt", "history", "memory"):
        subset = [(k, v) for k, v in templates.items() if k[0] == src]
        print(f"  [{src}] unique={len(subset)} instances={sum(v for _, v in subset)}")

    print("\n=== corrective clauses (prompt sentences starting 단,/다만) -> control purity ===")
    for norm, controls in sorted(corrective.items(), key=lambda x: -len(x[1])):
        c = Counter(controls)
        purity = max(c.values()) / len(controls)
        print(f"  n={len(controls):3} purity={purity:.2f} {dict(c)} | {norm[:90]}")

    print("\n=== full prompt template inventory (by frequency) ===")
    for (src, norm), n in templates.most_common():
        if src != "prompt":
            continue
        print(f"  {n:3}x | {norm[:110]}")

    print("\n=== history templates (top 40) ===")
    shown = 0
    for (src, norm), n in templates.most_common():
        if src != "history":
            continue
        print(f"  {n:3}x | {norm[:110]}")
        shown += 1
        if shown >= 40:
            break

    print("\n=== memory templates ===")
    for (src, norm), n in templates.most_common():
        if src == "memory":
            print(f"  {n:3}x | {norm[:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
