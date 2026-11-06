#!/usr/bin/env python3
"""Apply the year's legal limits to a ledger and compute what counts.

The model sorts costs into categories. This script applies the numbers the
law fixes: shares, caps, lump sums, the low-value asset limit, the
first-year month cut and the year-of-payment rule. Values come from
references/thresholds.json, each with its official source.

Usage:
  limits.py LEDGER.csv --year 2025

Ledger columns: date (YYYY-MM-DD), category, description, amount, plus optional
person, work_share (0..1, default 1), labor_cost, paid_by (bank|cash|card),
useful_life_years, vat_rate, currency (default EUR; anything else is flagged),
status (only "approved" passes the gate; "rejected" never counts).

Categories:
  telecom              phone/internet bill; bills and credits of a month are netted,
                       then 20 % flat, max 20 EUR per month; a work_share below 1
                       means a proven share (three-month log) instead
  home_office_days     amount = number of days; 6 EUR per day, max 1 260 EUR
  work_equipment       gross price; full deduction if net <= 800 EUR (vat_rate
                       column, default 19 %), useful_life_years 1 for computer
                       hardware/software, else depreciation with months cut in year 1
  software, training, travel, fees, tax_software, other_work
                       amount x work_share
  union_dues           counted on top of the employee lump sum
  business_expense     self-employed costs (EÜR), kept apart from employee costs
  household_services   § 35a (2): 20 % of labour cost, max 4 000 EUR, paid by bank
  craftsman            § 35a (3): 20 % of labour cost, max 1 200 EUR, paid by bank
  rental_*             rental costs, counted in the year paid (§ 11 EStG)
  rental_building      purchase price of the flat; never a yearly cost (see afa.py)
  rental_reserve       Hausgeld share paid into the owners' reserve; not deductible when paid
  private              recorded on purpose as not deductible
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxlib import eur, load_thresholds, read_ledger  # noqa: E402

D = Decimal
CENT = D("0.01")
SHARE_CATEGORIES = {"software", "training", "travel", "fees", "tax_software", "other_work"}


def r2(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def equipment_amount(row: dict, year: int, t: dict) -> tuple[Decimal, str]:
    gross = row["amount"] * row["work_share"]
    bought = date.fromisoformat(row["date"])
    vat = D(row["vat_rate"]) if row.get("vat_rate") not in (None, "") else D(t["vat_rate"])
    net = row["amount"] / (1 + vat)
    vat_note = "" if row.get("vat_rate") not in (None, "") else f" (assumed {vat * 100:.0f} % VAT; set vat_rate=0 for a private seller)"
    if not vat_note == "" and D(t["gwg_net"]) < row["amount"] <= D(t["gwg_net"]) * (1 + vat):
        return D(0), "NEEDS vat_rate: the result depends on the VAT on this invoice (0 for a private seller)"
    if net <= D(t["gwg_net"]):
        if bought.year == year:
            return r2(gross), f"net {eur(net)} <= {t['gwg_net']}: full deduction in year of purchase{vat_note}"
        return D(0), f"low-value item, fully deducted in {bought.year}"
    life = row.get("useful_life_years")
    if not life:
        return D(0), "NEEDS useful_life_years: net price above the low-value limit"
    if D(life) == 1:
        # Computer hardware and software: 1-year useful life, full deduction in the
        # year of purchase (BMF letter of 22.02.2022, BStBl I p. 187).
        return (r2(gross) if bought.year == year else D(0)), "useful life 1 year (computer hardware/software): full deduction in year of purchase"
    sched = dict(linear_schedule(gross, bought, D(life)))
    note = f"depreciation over {life} years from {bought:%m/%Y}"
    if year == bought.year:
        note += f": {13 - bought.month}/12 of the yearly amount in year 1"
    return r2(sched.get(year, D(0))), note


def linear_schedule(cost: Decimal, start: date, life: Decimal):
    """Straight-line plan; year 1 loses the full months before purchase (§ 7 Abs. 1 Satz 4)."""
    annual = cost / life
    left, y = cost, start.year
    first = annual * D(13 - start.month) / 12
    yield y, first
    left -= first
    while left > CENT / 2:
        y += 1
        part = min(annual, left)
        yield y, part
        left -= part


def year_edge_flag(paid: date, year: int) -> str:
    msg = f"paid in {paid.year}: counts in {paid.year} (§ 11 EStG)"
    near = (paid.year == year + 1 and paid.month == 1 and paid.day <= 10) or \
           (paid.year == year - 1 and paid.month == 12 and paid.day >= 22)
    if near:
        msg += (f"; a regular payment that belongs to {year} and was both due and paid within 10 days"
                f" of the turn of the year counts in {year} (§ 11 Abs. 2 Satz 2, Abs. 1 Satz 2)")
    return msg


def apply(rows: list[dict], year: int, require_approved: bool = True) -> tuple[list[dict], dict]:
    """Apply the year's limits. Rows with status 'rejected' never count. With
    require_approved, every row that is not 'approved' is flagged."""
    t = load_thresholds(year)
    out, totals = [], defaultdict(D)
    ho_days = defaultdict(D)
    telecom_groups = defaultdict(list)
    for row in rows:
        cat = row["category"].strip()
        person = (row.get("person") or "all").strip() or "all"
        paid = date.fromisoformat(row["date"])
        status = (row.get("status") or "").strip().lower()
        amt, note = D(0), ""
        flags = []
        rec = {**row, "counted": D(0), "note": "", "flags": ""}
        out.append(rec)
        if status == "rejected":
            rec["note"] = "rejected: not counted"
            continue
        if require_approved and status != "approved":
            flags.append("not approved yet: set status=approved after review")
        cur = (row.get("currency") or "EUR").strip().upper()
        if cur != "EUR":
            flags.append(f"amount in {cur}: convert to EUR at the payment date, then re-run")
        elif cat == "rental_building":
            note = "purchase price: not a yearly cost, use afa.py for depreciation"
        elif cat == "rental_reserve":
            note = ("owners' reserve (Erhaltungsrücklage) share of Hausgeld: not deductible when paid, "
                    "only when the reserve is spent on repairs (BFH IX R 19/24)")
        elif cat != "work_equipment" and paid.year != year:
            flags.append(year_edge_flag(paid, year))
        elif cat == "telecom":
            telecom_groups[(person, row["date"][:7])].append(rec)
            note = "see monthly telecom total"
        elif cat == "home_office_days":
            ho_days[person] += row["amount"]
            note = "days, cap applied in the total"
        elif cat == "work_equipment":
            amt, note = equipment_amount(row, year, t)
            if note.startswith("NEEDS"):
                flags.append(note)
            totals[f"work:{person}"] += amt
        elif cat in SHARE_CATEGORIES:
            amt = row["amount"] * row["work_share"]
            note = f"work share {row['work_share']}"
            totals[f"work:{person}"] += amt
        elif cat == "union_dues":
            amt = row["amount"]
            if t.get("union_dues_on_top"):
                totals[f"union:{person}"] += amt
                note = "union dues: counted on top of the lump sum (§ 9a Satz 3)"
            else:
                totals[f"work:{person}"] += amt
                note = "union dues: ordinary work cost in this year"
        elif cat == "business_expense":
            amt = row["amount"] * row["work_share"]
            totals[f"business:{person}"] += amt
            note = "business cost (EÜR): separate from employee costs"
        elif cat in {"household_services", "craftsman"}:
            if (row.get("paid_by") or "").strip().lower() not in {"bank", "transfer", "ueberweisung"}:
                flags.append("§ 35a needs payment to the provider's account (paid_by=bank)")
            elif row["labor_cost"] is None:
                flags.append("§ 35a counts labour only: fill labor_cost from the invoice")
            elif not (D(0) <= row["labor_cost"] <= row["amount"]):
                flags.append("labor_cost must be between 0 and the invoice amount")
            else:
                amt = row["labor_cost"]
                totals[cat] += amt
                note = "labour cost counted"
        elif cat.startswith("rental_"):
            amt = row["amount"]
            totals["rental"] += amt
            note = "rental cost, year of payment"
        elif cat == "private":
            note = "not deductible (recorded on purpose)"
        else:
            flags.append(f"unknown category {cat!r}")
        rec.update(counted=r2(amt), note=note or rec["note"], flags="; ".join(flags))

    # Telecom: credits and bills of one month are netted first, then the cap applies.
    share, cap = D(t["telecom_share"]), D(t["telecom_month_cap"])
    for (person, month), group in telecom_groups.items():
        proven = [r for r in group if r["work_share"] != 1]
        flat = [r for r in group if r["work_share"] == 1]
        for r in proven:
            r["counted"] = r2(r["amount"] * r["work_share"])
            r["note"] = "proven work share (keep the three-month log, R 9.1 Abs. 5 LStR)"
        gross = sum((r["amount"] for r in flat), D(0))
        flat_total = r2(min(max(gross, D(0)) * share, cap)) if flat else D(0)
        for r in flat:
            r["counted"] = r2(flat_total * r["amount"] / gross) if gross > 0 else D(0)
            r["note"] = f"{share * 100:.0f} % of the month's bills, max {cap} EUR per month"
        if proven and flat:
            for r in group:
                r["flags"] = "; ".join(x for x in (r["flags"], f"{month}: flat rule and proven share mixed; use one method per month") if x)
        totals[f"work:{person}"] += flat_total + sum((r["counted"] for r in proven), D(0))

    summary: dict = {}
    for person, days in ho_days.items():
        ho = min(days * D(t["home_office_day"]), D(t["home_office_cap"]))
        totals[f"work:{person}"] += ho
        summary[f"home office {person}"] = f"{days} days x {t['home_office_day']} = {eur(ho)} (cap {t['home_office_cap']})"
    lump = D(t["employee_lump_sum"])
    people = sorted({k.split(":", 1)[1] for k in totals if k.startswith(("work:", "union:"))})
    for person in people:
        val, union = totals[f"work:{person}"], totals[f"union:{person}"]
        verdict = "itemize" if val > lump else "lump sum wins"
        line = f"{eur(val)} vs lump sum {eur(lump)}: {verdict}"
        if union:
            line += f"; plus union dues {eur(union)} either way"
        summary[f"work costs {person}"] = line
    for key in sorted(k for k in totals if k.startswith("business:")):
        summary[f"business costs {key.split(':', 1)[1]}"] = f"{eur(totals[key])} (EÜR, not compared with the lump sum)"
    for cat, rate, cap_key in (("household_services", "household_services_rate", "household_services_cap"),
                               ("craftsman", "craftsman_rate", "craftsman_cap")):
        if totals[cat]:
            cut = min(totals[cat] * D(t[rate]), D(t[cap_key]))
            summary[cat] = f"labour {eur(totals[cat])} -> tax cut {eur(cut)} (cap {t[cap_key]})"
    if totals["rental"]:
        summary["rental costs"] = eur(totals["rental"])
    return out, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ledger", type=Path)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--draft", action="store_true", help="do not flag rows that are not approved yet")
    a = ap.parse_args()
    rows, summary = apply(read_ledger(a.ledger), a.year, require_approved=not a.draft)
    print(f"## Limits applied for {a.year}\n")
    print("| date | category | amount | counted | note | flags |")
    print("|---|---|---:|---:|---|---|")
    for r in rows:
        print(f"| {r['date']} | {r['category']} | {eur(r['amount'])} | {eur(r['counted'])} | {r['note']} | {r['flags']} |")
    print("\n## Totals\n")
    for k, v in summary.items():
        print(f"- {k}: {v}")
    flagged = [r for r in rows if r["flags"]]
    print(f"\n{len(flagged)} row(s) flagged for a human decision.")
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
