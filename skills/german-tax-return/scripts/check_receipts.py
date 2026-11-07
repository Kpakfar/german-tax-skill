#!/usr/bin/env python3
"""Check that every claimed amount appears in its source document.

The model may suggest a number. This script decides whether the document
backs it. A row passes only when the exact amount (to the cent) is found in
the text of the file named in the `source` column. It is a presence check:
the digits must be on the document. Whether the document is the right one,
and whether the cost is deductible, stays a human question. A document that
names only a foreign currency is flagged CHECK CURRENCY.

Usage:
  check_receipts.py LEDGER.csv [--root DIR] [--tolerance 0.00]

Ledger columns (CSV, header row): date, category, description, amount, source
Extra columns are ignored. `source` is a path relative to --root (default: the
ledger's folder). Several files can be joined with "|".

If labor_cost is filled (§ 35a), it must also appear in the same document.
Exit code 0 = every row backed, 1 = at least one row failed. Use it as a gate.
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxlib import amounts_in, doc_text, eur, foreign_currency_only, read_ledger  # noqa: E402


def check(ledger: Path, root: Path, tolerance: Decimal) -> list[dict]:
    results = []
    cache: dict[Path, str | None] = {}
    for row in read_ledger(ledger):
        want = abs(row["amount"]).quantize(Decimal("0.01"))
        sources = [s.strip() for s in (row.get("source") or "").split("|") if s.strip()]
        status, where = "NO SOURCE", ""
        if sources:
            status = "NOT FOUND"
            for s in sources:
                p = (root / s).resolve()
                if not p.exists():
                    status, where = "MISSING FILE", s
                    continue
                if p not in cache:
                    cache[p] = doc_text(p)
                text = cache[p]
                if text is None:
                    status, where = "UNREADABLE", s
                    continue
                found = amounts_in(text)
                if any(abs(a - want) <= tolerance for a in found):
                    labor = row.get("labor_cost")
                    if labor is not None and not any(abs(a - abs(labor).quantize(Decimal("0.01"))) <= tolerance for a in found):
                        status, where = "LABOUR NOT FOUND", s
                        continue
                    if (row.get("currency") or "EUR").strip().upper() == "EUR" and foreign_currency_only(text):
                        status, where = "CHECK CURRENCY", s
                        continue
                    status, where = "OK", s
                    break
                where = s
        results.append({**row, "status_check": status, "matched_in": where})
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ledger", type=Path)
    ap.add_argument("--root", type=Path)
    ap.add_argument("--tolerance", type=Decimal, default=Decimal("0.00"))
    a = ap.parse_args()
    root = a.root or a.ledger.parent
    res = check(a.ledger, root, a.tolerance)
    ok = sum(r["status_check"] == "OK" for r in res)
    print("| status | date | category | amount | description | source |")
    print("|---|---|---|---:|---|---|")
    for r in res:
        print(f"| {r['status_check']} | {r['date']} | {r['category']} | {eur(r['amount'])} | {r['description']} | {r['matched_in']} |")
    print(f"\n{ok} of {len(res)} amounts found in their source document.")
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
