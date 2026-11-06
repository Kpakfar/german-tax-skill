#!/usr/bin/env python3
"""Monthly scan: payments, invoices and emails -> deductible candidates.

Run once a month. It reads the bank export, the invoice folder and saved
emails, matches payments to receipts by exact amount, sorts them with your
rules, and writes a short report plus proposed ledger rows. Nothing becomes a
claim until a human changes its status to "approved" in the ledger.

Usage:
  monthly_scan.py --month 2026-10 --bank bank.csv --bank-format bank-format.json \
      --rules rules.json --docs invoices/ [--emails mail/] \
      --ledger ledger-2026.csv --out reports/

bank-format.json maps your bank's CSV columns, for example:
  {"delimiter": ";", "encoding": "utf-8", "skip_lines": 0,
   "date_col": "Buchungstag", "date_format": "%d.%m.%Y",
   "amount_col": "Betrag", "counterparty_col": "Beguenstigter/Zahlungspflichtiger",
   "purpose_col": "Verwendungszweck"}

rules.json is a list of {"match": "regex", "category": "...", "work_share": "1",
"note": "..."}; the first match wins. See rules.example.json.
"""
from __future__ import annotations

import argparse
import csv
import email
import email.policy
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxlib import LEDGER_FIELDS, amounts_in, doc_text, eur, parse_amount, read_ledger  # noqa: E402
import limits  # noqa: E402

INVOICE_WORDS = re.compile(r"rechnung|invoice|receipt|quittung|beleg|abrechnung|zahlungsbest", re.I)


def load_bank(path: Path, fmt: dict) -> list[dict]:
    with path.open(encoding=fmt.get("encoding", "utf-8"), newline="") as fh:
        for _ in range(int(fmt.get("skip_lines", 0))):
            next(fh)
        rows = []
        for r in csv.DictReader(fh, delimiter=fmt.get("delimiter", ";")):
            raw_date = (r.get(fmt["date_col"]) or "").strip()
            if not raw_date:
                continue
            rows.append({
                "date": datetime.strptime(raw_date, fmt.get("date_format", "%d.%m.%Y")).date(),
                "amount": parse_amount(r[fmt["amount_col"]]),
                "counterparty": (r.get(fmt["counterparty_col"]) or "").strip(),
                "purpose": (r.get(fmt.get("purpose_col", ""), "") or "").strip(),
            })
    return rows


def payee_key(tx: dict) -> str:
    words = re.sub(r"[^a-zäöüß ]", " ", tx["counterparty"].lower()).split()
    return " ".join(words[:3])


def classify(tx: dict, rules: list[dict]) -> dict | None:
    hay = f"{tx['counterparty']} {tx['purpose']}"
    for rule in rules:
        if re.search(rule["match"], hay, re.I):
            return rule
    return None


def load_docs(folders: list[Path]) -> list[dict]:
    docs = []
    for folder in folders:
        if not folder or not folder.exists():
            continue
        for p in sorted(folder.rglob("*")):
            if not p.is_file() or p.name.startswith("."):
                continue
            text = doc_text(p)
            if text is None:
                continue
            sent = None
            if p.suffix.lower() == ".eml":
                msg = email.message_from_bytes(p.read_bytes(), policy=email.policy.default)
                try:
                    sent = parsedate_to_datetime(msg["date"]).date() if msg["date"] else None
                except (TypeError, ValueError):
                    sent = None
            if sent is None:
                m = re.search(r"(20\d\d)-(\d\d)(?:-(\d\d))?", p.name)
                if m:
                    sent = date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
                else:
                    sent = date.fromtimestamp(p.stat().st_mtime)
            docs.append({"path": p, "text": text, "amounts": amounts_in(text),
                         "is_invoice": bool(INVOICE_WORDS.search(text)), "sent": sent})
    return docs


def find_receipt(docs: list[dict], tx: dict, used: set) -> tuple[dict | None, str]:
    """Invoice with the same amount, not used yet, within 45 days of the payment.
    Prefers a document that names the payee. Returns (doc, note)."""
    amount = abs(tx["amount"]).quantize(Decimal("0.01"))
    pool = [d for d in docs if d["is_invoice"] and d["path"] not in used and amount in d["amounts"]
            and abs((d["sent"] - tx["date"]).days) <= 45]
    if not pool:
        return None, ""
    words = [w for w in re.findall(r"[a-zäöüß]{4,}", tx["counterparty"].lower())][:2]
    named = [d for d in pool if any(w in d["text"].lower() for w in words)]
    best = named or pool
    best.sort(key=lambda d: abs((d["sent"] - tx["date"]).days))
    note = ""
    if not named:
        note = "payee not named on the document: check by eye"
    elif len(named) > 1 and abs((named[0]["sent"] - tx["date"]).days) == abs((named[1]["sent"] - tx["date"]).days):
        note = f"ambiguous: also {named[1]['path'].name}"
    return best[0], note


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--bank", type=Path, required=True)
    ap.add_argument("--bank-format", type=Path, required=True)
    ap.add_argument("--rules", type=Path, required=True)
    ap.add_argument("--docs", type=Path, required=True)
    ap.add_argument("--emails", type=Path)
    ap.add_argument("--ledger", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    year, month = (int(x) for x in a.month.split("-"))
    fmt = json.loads(a.bank_format.read_text(encoding="utf-8"))
    rules = json.loads(a.rules.read_text(encoding="utf-8"))
    txs = load_bank(a.bank, fmt)
    docs = load_docs([a.docs, a.emails])
    month_txs = [t for t in txs if (t["date"].year, t["date"].month) == (year, month)]

    # Payees seen in two or more months: subscriptions and contracts.
    months_by_payee = defaultdict(set)
    for t in txs:
        if t["amount"] < 0:
            months_by_payee[payee_key(t)].add((t["date"].year, t["date"].month))

    # Only deductible candidates may claim a receipt, so private payments never use one up.
    candidates, unruled, used_docs = [], [], set()
    for t in month_txs:
        rule = classify(t, rules)
        if rule is None:
            if t["amount"] < 0 and len(months_by_payee[payee_key(t)]) >= 2:
                unruled.append(t)
            continue
        if rule["category"] == "private":
            continue
        receipt, note = find_receipt(docs, t, used_docs)
        if receipt:
            used_docs.add(receipt["path"])
        candidates.append((t, rule, receipt, note))

    # Invoices that arrived this month but match no bank payment (card, PayPal, cash).
    loose = [d for d in docs if d["is_invoice"] and d["path"] not in used_docs
             and d["sent"] and (d["sent"].year, d["sent"].month) == (year, month)]

    # Append proposals to the ledger; never touch rows a human already decided.
    existing = read_ledger(a.ledger) if a.ledger.exists() else []
    from collections import Counter
    have = Counter((r["date"], r["amount"].quantize(Decimal("0.01")), r["description"]) for r in existing)
    run = Counter()
    new_rows = []
    for t, rule, receipt, _ in candidates:
        desc = f"{t['counterparty']} {t['purpose']}".strip()[:80]
        cost = (-t["amount"]).quantize(Decimal("0.01"))   # payment > 0, refund < 0
        key = (t["date"].isoformat(), cost, desc)
        run[key] += 1
        if run[key] <= have[key]:   # already in the ledger (re-run), keep identical real payments
            continue
        src = ""
        if receipt:
            try:
                src = str(receipt["path"].resolve().relative_to(a.ledger.parent.resolve()))
            except ValueError:
                src = str(receipt["path"].resolve())
        new_rows.append({"date": t["date"].isoformat(), "category": rule["category"], "description": desc,
                         "amount": f"{cost:.2f}", "source": src, "person": rule.get("person", ""),
                         "work_share": rule.get("work_share", "1"), "labor_cost": "", "paid_by": "bank",
                         "useful_life_years": rule.get("useful_life_years", ""), "vat_rate": "",
                         "currency": "EUR", "status": "proposed"})
    if new_rows:
        if a.ledger.exists():
            with a.ledger.open(encoding="utf-8", newline="") as fh:
                header = next(csv.reader(fh), LEDGER_FIELDS)
            missing = [f for f in LEDGER_FIELDS if f not in header]
            if missing:
                print(f"warning: ledger has no column(s) {', '.join(missing)}; those values are dropped", file=sys.stderr)
        else:
            header = LEDGER_FIELDS
            with a.ledger.open("w", encoding="utf-8", newline="") as fh:
                csv.DictWriter(fh, fieldnames=header).writeheader()
        with a.ledger.open("a", encoding="utf-8", newline="") as fh:
            csv.DictWriter(fh, fieldnames=header, extrasaction="ignore").writerows(new_rows)

    # Year to date: this year's rows plus equipment from earlier years that still depreciates.
    ytd = [r for r in read_ledger(a.ledger)
           if r["date"].startswith(str(year)) or (r["category"] == "work_equipment" and r["date"][:4] < str(year))
           ] if a.ledger.exists() else []
    _, summary = limits.apply(ytd, year, require_approved=False) if ytd else ([], {})

    a.out.mkdir(parents=True, exist_ok=True)
    report = a.out / f"{a.month}.md"
    L = [f"# Tax scan {a.month}", "",
         f"{len(month_txs)} payments, {len(candidates)} deductible candidates (refunds included), "
         f"{sum(1 for c in candidates if not c[2])} without receipt, {len(unruled)} recurring payments without a rule, "
         f"{len(loose)} invoices without a bank match.", "",
         "## Candidates (status: proposed, approve in the ledger)", "",
         "| date | category | cost | payee | receipt | check |", "|---|---|---:|---|---|---|"]
    for t, rule, receipt, note in candidates:
        L.append(f"| {t['date']} | {rule['category']} | {eur(-t['amount'])} | {t['counterparty']} | "
                 f"{receipt['path'].name if receipt else '**MISSING**'} | {note} |")
    L += ["", "## Recurring payments without a rule: work or private?", ""]
    L += [f"- {t['date']} {t['counterparty']} {eur(abs(t['amount']))}: add a rule to rules.json" for t in unruled] or ["- none"]
    L += ["", "## Invoices this month with no bank payment (card, PayPal, cash?)", ""]
    L += [f"- {d['path'].name}" for d in loose] or ["- none"]
    L += ["", f"## Year to date {year} (if every proposed row is approved; rejected rows excluded)", ""]
    L += [f"- {k}: {v}" for k, v in summary.items()] or ["- no rows yet"]
    L += ["", "Costs count in the year they are paid (§ 11 EStG). Keep every receipt."]
    report.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"report: {report}\nproposed rows added: {len(new_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
