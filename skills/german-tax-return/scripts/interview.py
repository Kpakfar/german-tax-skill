#!/usr/bin/env python3
"""Screening interview: 12 questions -> what to gather, which costs to track, which forms.

The questions live in references/interview.json. This script only turns
answers into a checklist, so the same answers always give the same list.

Usage:
  interview.py --ask                     ask the questions in the terminal
  interview.py --answers answers.json    {"employment": "yes", "rental": "no", ...}
  interview.py --template                print an empty answers file

Answers: yes, no, or unsure ("unsure" counts as yes: gather first, decide later).
A blank answer is unanswered, not no. Anything else is an error.
"status" holds the free-text answer to question 1 (tax year, alone or joint).
Output: a Markdown checklist on stdout (prompts go to stderr, so
`interview.py --ask > gather.md` works). Exit code 1 while any question is open.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

QUESTIONS = Path(__file__).resolve().parent.parent / "references" / "interview.json"
YES = {"yes", "y", "ja", "j", "unsure", "?", "maybe", "weiß nicht"}
NO = {"no", "n", "nein"}


def load() -> list[dict]:
    return json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]


def normalize(answers: dict[str, str], questions: list[dict]) -> tuple[dict, list[str]]:
    """Blank means unanswered. Anything that is not yes/no/unsure is an error."""
    ids = {q["id"] for q in questions}
    clean, errors = {}, []
    for key, raw in answers.items():
        if key == "status":
            clean[key] = str(raw).strip()
            continue
        if key not in ids:
            errors.append(f"unknown question id {key!r}")
            continue
        v = str(raw).strip().lower()
        if not v:
            continue
        if v in YES:
            clean[key] = "yes"
        elif v in NO:
            clean[key] = "no"
        else:
            errors.append(f"{key}: {raw!r} is not yes, no or unsure")
    return clean, errors


def checklist(questions: list[dict], answers: dict[str, str]) -> str:
    answers, errors = normalize(answers, questions)
    if errors:
        raise SystemExit("Invalid answers: " + "; ".join(errors))
    open_areas = [q for q in questions if q.get("always") or answers.get(q["id"]) == "yes"]
    unanswered = [q["id"] for q in questions if not q.get("always") and q["id"] not in answers]
    if not answers.get("status"):
        unanswered.insert(0, "status")
    lines = ["# Tax return: areas to gather", ""]
    if answers.get("status"):
        lines += [f"Tax year and filing: {answers['status']}", ""]
    if unanswered:
        lines += [f"**GATE NOT PASSED. Not answered yet:** {', '.join(unanswered)}. "
                  "Answer every question before gathering stops.", ""]
    forms, cats = [], []
    for q in open_areas:
        lines += [f"## {q['id']}", "", f"*{q['ask']}*", "", "Ask next:"]
        lines += [f"- [ ] {f}" for f in q["follow_up"]]
        lines += ["", "Gather:"]
        lines += [f"- [ ] {g}" for g in q["gather"]]
        if q["categories"]:
            lines += ["", "Ledger categories: " + ", ".join(f"`{c}`" for c in q["categories"])]
        lines.append("")
        forms += [f for f in q["forms"] if f not in forms]
        cats += [c for c in q["categories"] if c not in cats]
    closed = [q["id"] for q in questions if answers.get(q["id"]) == "no"]
    lines += ["## Summary", "", "Forms likely needed: " + "; ".join(forms),
              "", "Costs to track in the ledger: " + (", ".join(cats) or "none"),
              "", "Closed (answered no): " + (", ".join(closed) or "none"), ""]
    return "\n".join(lines)


def unanswered_count(questions: list[dict], answers: dict) -> int:
    clean, _ = normalize(answers, questions)
    return sum(1 for q in questions if not q.get("always") and q["id"] not in clean) + (0 if clean.get("status") else 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ask", action="store_true")
    g.add_argument("--answers", type=Path)
    g.add_argument("--template", action="store_true")
    a = ap.parse_args()
    qs = load()
    if a.template:
        print(json.dumps({"status": "", **{q["id"]: "" for q in qs if not q.get("always")}}, indent=2))
        return 0
    if a.ask:
        answers = {}
        for i, q in enumerate(qs, 1):
            prompt = f"{i}. {q['ask']} " + ("" if q.get("always") else "[yes/no/unsure] ")
            while True:
                print(prompt, end="", file=sys.stderr, flush=True)
                raw = input().strip()
                if q.get("always"):
                    answers["status"] = raw
                    break
                if raw.lower() in YES | NO:
                    answers[q["id"]] = raw
                    break
                print("   please answer yes, no or unsure", file=sys.stderr)
    else:
        answers = json.loads(a.answers.read_text(encoding="utf-8"))
    print(checklist(qs, answers))
    return 1 if unanswered_count(qs, answers) else 0


if __name__ == "__main__":
    sys.exit(main())
