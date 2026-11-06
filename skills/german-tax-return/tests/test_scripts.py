"""Tests for the checking scripts. Run: python3 -m unittest discover -s tests

All data here is invented (Erika Musterfrau, Musterstraße). No real person.
"""
from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal as D
from email.message import EmailMessage
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import afa  # noqa: E402
import check_receipts  # noqa: E402
import interview  # noqa: E402
import limits  # noqa: E402
from taxlib import amounts_in, parse_amount  # noqa: E402

FIELDS = ["date", "category", "description", "amount", "source", "person",
          "work_share", "labor_cost", "paid_by", "useful_life_years", "vat_rate", "currency", "status"]


def write_ledger(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


class Amounts(unittest.TestCase):
    def test_german_and_english(self):
        self.assertEqual(parse_amount("1.234,56 €"), D("1234.56"))
        self.assertEqual(parse_amount("1,234.56"), D("1234.56"))
        self.assertEqual(parse_amount("-39,99"), D("-39.99"))
        self.assertEqual(parse_amount("12"), D("12"))
        self.assertEqual(parse_amount("1.234"), D("1234"))

    def test_find_in_text(self):
        found = amounts_in("Summe 1.199,00 EUR, MwSt 191,44 EUR, Total 1,008.40")
        self.assertTrue({D("1199.00"), D("191.44"), D("1008.40")} <= found)
        self.assertIn(D("1234.56"), amounts_in("Total 1234.56 USD"))
        self.assertNotIn(D("1.02"), amounts_in("Datum 01.02.2025"))
        self.assertIn(D("1234.00"), amounts_in("Summe 1.234 EUR"))


class Receipts(unittest.TestCase):
    def test_match_and_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "inv1.txt").write_text("Rechnung Nr. 7\nGesamtbetrag 39,99 EUR", encoding="utf-8")
            (t / "inv2.txt").write_text("Rechnung\nBetrag 20,00 EUR", encoding="utf-8")
            write_ledger(t / "l.csv", [
                {"date": "2025-03-01", "category": "telecom", "description": "phone", "amount": "39,99", "source": "inv1.txt"},
                {"date": "2025-04-01", "category": "software", "description": "tool", "amount": "21,00", "source": "inv2.txt"},
                {"date": "2025-05-01", "category": "software", "description": "tool", "amount": "5,00", "source": "gone.txt"},
            ])
            res = check_receipts.check(t / "l.csv", t, D("0"))
            self.assertEqual([r["status_check"] for r in res], ["OK", "NOT FOUND", "MISSING FILE"])

    def test_labour_must_be_on_invoice(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "inv.txt").write_text("Rechnung\nArbeitskosten 80,00 EUR\nGesamt 100,00 EUR", encoding="utf-8")
            write_ledger(t / "l.csv", [
                {"date": "2025-03-01", "category": "craftsman", "description": "ok", "amount": "100,00", "labor_cost": "80,00", "source": "inv.txt"},
                {"date": "2025-03-01", "category": "craftsman", "description": "bad", "amount": "100,00", "labor_cost": "95,00", "source": "inv.txt"},
            ])
            res = check_receipts.check(t / "l.csv", t, D("0"))
            self.assertEqual([r["status_check"] for r in res], ["OK", "LABOUR NOT FOUND"])


class Limits(unittest.TestCase):
    def run_rows(self, rows, year=2025):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "l.csv"
            write_ledger(p, rows)
            from taxlib import read_ledger
            return limits.apply(read_ledger(p), year, require_approved=False)

    def apply_strict(self, rows, year=2025):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "l.csv"
            write_ledger(p, rows)
            from taxlib import read_ledger
            return limits.apply(read_ledger(p), year)

    def test_telecom_cap(self):
        out, _ = self.run_rows([
            {"date": "2025-01-10", "category": "telecom", "description": "a", "amount": "50,00"},
            {"date": "2025-02-10", "category": "telecom", "description": "b", "amount": "150,00"},
        ])
        self.assertEqual([r["counted"] for r in out], [D("10.00"), D("20.00")])

    def test_telecom_cap_is_per_month_for_all_bills(self):
        out, _ = self.run_rows([
            {"date": "2025-03-05", "category": "telecom", "description": "phone", "amount": "60,00"},
            {"date": "2025-03-20", "category": "telecom", "description": "internet", "amount": "60,00"},
        ])
        self.assertEqual(sum(r["counted"] for r in out), D("20.00"))

    def test_home_office_cap(self):
        _, s = self.run_rows([{"date": "2025-12-31", "category": "home_office_days", "description": "d", "amount": "230", "person": "a"}])
        self.assertIn("1.260,00", s["home office a"])

    def test_low_value_item(self):
        out, _ = self.run_rows([
            {"date": "2025-06-01", "category": "work_equipment", "description": "screen", "amount": "952,00", "vat_rate": "0.19"},
            {"date": "2025-06-02", "category": "work_equipment", "description": "mouse", "amount": "49,00"},
        ])
        self.assertEqual([r["counted"] for r in out], [D("952.00"), D("49.00")])

    def test_chair_bought_in_december(self):
        row = {"date": "2024-12-15", "category": "work_equipment", "description": "chair", "amount": "1300,00", "useful_life_years": "13"}
        y1, _ = self.run_rows([row], 2024)
        y2, _ = self.run_rows([row], 2025)
        self.assertEqual(y1[0]["counted"], D("8.33"))   # 100 per year x 1/12
        self.assertEqual(y2[0]["counted"], D("100.00"))

    def test_household_needs_bank(self):
        out, s = self.run_rows([
            {"date": "2025-07-01", "category": "household_services", "description": "stairs", "amount": "500", "labor_cost": "400", "paid_by": "bank"},
            {"date": "2025-07-02", "category": "craftsman", "description": "cash job", "amount": "300", "paid_by": "cash"},
        ])
        self.assertIn("80,00", s["household_services"])
        self.assertTrue(out[1]["flags"])

    def test_wrong_year(self):
        out, _ = self.run_rows([{"date": "2026-01-05", "category": "rental_hausgeld", "description": "Dez", "amount": "300"}])
        self.assertIn("§ 11", out[0]["flags"])

    def test_foreign_currency_flagged(self):
        out, _ = self.run_rows([{"date": "2025-03-01", "category": "software", "description": "x", "amount": "23,80", "currency": "USD"}])
        self.assertIn("convert to EUR", out[0]["flags"])

    def test_purchase_price_is_not_a_cost(self):
        out, s = self.run_rows([{"date": "2025-03-01", "category": "rental_building", "description": "flat", "amount": "300000"}])
        self.assertEqual(out[0]["counted"], D("0.00"))

    def test_35a_without_labour_cost_is_flagged(self):
        out, s = self.run_rows([{"date": "2025-07-01", "category": "craftsman", "description": "x", "amount": "1000", "paid_by": "bank"}])
        self.assertEqual(out[0]["counted"], D("0.00"))
        self.assertIn("labor_cost", out[0]["flags"])

    def test_telecom_mixed_methods(self):
        out, s = self.run_rows([
            {"date": "2025-04-01", "category": "telecom", "description": "phone", "amount": "40", "work_share": "0.5", "person": "a"},
            {"date": "2025-04-02", "category": "telecom", "description": "internet", "amount": "100", "person": "a"},
        ])
        self.assertEqual(sum(r["counted"] for r in out), D("40.00"))   # 20 proven + 20 capped flat
        self.assertIn("mixed", out[1]["flags"])

    def test_labour_cannot_exceed_invoice(self):
        out, _ = self.run_rows([{"date": "2025-07-01", "category": "craftsman", "description": "x", "amount": "100", "labor_cost": "10000", "paid_by": "bank"}])
        self.assertEqual(out[0]["counted"], D("0.00"))
        self.assertTrue(out[0]["flags"])

    def test_vat_unknown_near_limit(self):
        out, _ = self.run_rows([{"date": "2025-06-01", "category": "work_equipment", "description": "x", "amount": "900"}])
        self.assertIn("NEEDS vat_rate", out[0]["flags"])

    def test_status_gate(self):
        out, s = self.apply_strict([
            {"date": "2025-03-01", "category": "software", "description": "a", "amount": "2000", "status": "rejected"},
            {"date": "2025-03-02", "category": "software", "description": "b", "amount": "10", "status": "proposed"},
            {"date": "2025-03-03", "category": "software", "description": "c", "amount": "20", "status": "approved"},
        ])
        self.assertEqual(out[0]["counted"], D("0.00"))
        self.assertIn("not approved", out[1]["flags"])
        self.assertEqual(out[2]["flags"], "")

    def test_reserve_not_deductible(self):
        out, _ = self.run_rows([{"date": "2025-05-01", "category": "rental_reserve", "description": "r", "amount": "400"}])
        self.assertEqual(out[0]["counted"], D("0.00"))

    def test_telecom_credit_order_independent(self):
        a = [{"date": "2025-04-01", "category": "telecom", "description": "bill", "amount": "150"},
             {"date": "2025-04-20", "category": "telecom", "description": "credit", "amount": "-50"}]
        x, _ = self.run_rows(a)
        y, _ = self.run_rows(list(reversed(a)))
        self.assertEqual(sum(r["counted"] for r in x), sum(r["counted"] for r in y))
        self.assertEqual(sum(r["counted"] for r in x), D("20.00"))

    def test_private_seller_no_vat(self):
        out, _ = self.run_rows([{"date": "2025-06-01", "category": "work_equipment", "description": "used", "amount": "900", "vat_rate": "0"}])
        self.assertIn("NEEDS useful_life_years", out[0]["flags"])

    def test_computer_one_year(self):
        out, _ = self.run_rows([{"date": "2025-11-01", "category": "work_equipment", "description": "laptop", "amount": "1800", "useful_life_years": "1"}])
        self.assertEqual(out[0]["counted"], D("1800.00"))

    def test_union_dues_by_year(self):
        row = [{"date": "2026-02-01", "category": "union_dues", "description": "u", "amount": "300", "person": "a"}]
        _, s26 = self.run_rows(row, 2026)
        self.assertIn("plus union dues", s26["work costs a"])
        row[0]["date"] = "2025-02-01"
        _, s25 = self.run_rows(row, 2025)
        self.assertNotIn("plus union dues", s25["work costs a"])

    def test_lump_sum(self):
        _, s = self.run_rows([{"date": "2025-03-01", "category": "software", "description": "x", "amount": "200", "person": "a"}])
        self.assertIn("lump sum wins", s["work costs a"])


class Afa(unittest.TestCase):
    def test_split(self):
        r = afa.split(D("400000"), D("50"), D("1200"), D("340000"))
        self.assertEqual(r["building_share_pct"], D("85.00"))
        self.assertEqual(r["price_to_building"], D("340000.00"))

    def test_unverified_year_refused(self):
        with self.assertRaises(SystemExit):
            afa.schedule(D("100000"), date(2099, 1, 1), "linear3", 2, 2099)

    def test_window(self):
        self.assertTrue(afa.eligible(date(2024, 3, 1), None, 2025)[0])
        self.assertFalse(afa.eligible(date(2023, 9, 30), None, 2025)[0])

    def test_declining_first_year(self):
        rows = afa.schedule(D("300000"), date(2025, 2, 1), "declining5", 2, 2025)
        self.assertEqual(rows[0][1], D("13750.00"))       # 5 % x 11/12
        self.assertEqual(rows[1][1], D("14312.50"))       # 5 % of 286 250


class Interview(unittest.TestCase):
    def test_twelve_questions_and_branches(self):
        qs = interview.load()
        self.assertEqual(len(qs), 12)
        out = interview.checklist(qs, {"rental": "yes", "employment": "no", "telecom": "unsure"})
        self.assertIn("Anlage V", out)
        self.assertIn("telecom", out)                 # unsure counts as yes
        self.assertNotIn("Lohnsteuerbescheinigung", out)
        self.assertIn("Not answered yet", out)

    def test_blank_is_unanswered_and_invalid_fails(self):
        qs = interview.load()
        out = interview.checklist(qs, {"rental": ""})
        self.assertIn("rental", out.split("Not answered yet")[1].split("\n")[0])
        self.assertIn("Closed (answered no): none", out)
        with self.assertRaises(SystemExit):
            interview.checklist(qs, {"rental": "perhaps"})

    def test_categories_exist_in_limits(self):
        known = limits.SHARE_CATEGORIES | {"telecom", "home_office_days", "work_equipment", "union_dues",
                                           "business_expense", "household_services", "craftsman", "private"}
        for q in interview.load():
            for c in q["categories"]:
                self.assertTrue(c in known or c.startswith("rental_"), c)


class Monthly(unittest.TestCase):
    def test_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "docs").mkdir(); (t / "mail").mkdir()
            (t / "docs" / "2025-09_telekom.txt").write_text("Telekom Rechnung September\nBetrag 44,95 EUR", encoding="utf-8")
            (t / "docs" / "2025-10_telekom.txt").write_text("Telekom Rechnung Oktober\nBetrag 44,95 EUR", encoding="utf-8")
            msg = EmailMessage()
            msg["Subject"] = "Your receipt from Example AI"
            msg["From"] = "billing@example.com"
            msg["Date"] = "Tue, 14 Oct 2025 10:00:00 +0200"
            msg.set_content("Receipt\nTotal 23,80 EUR")
            (t / "mail" / "r.eml").write_bytes(bytes(msg))
            with (t / "bank.csv").open("w", encoding="utf-8") as fh:
                fh.write("Buchungstag;Beguenstigter/Zahlungspflichtiger;Verwendungszweck;Betrag\n")
                fh.write("02.09.2025;Streamco Media;Abo;-9,99\n")
                fh.write("02.10.2025;Streamco Media;Abo;-9,99\n")
                fh.write("05.10.2025;Telekom Deutschland;Rechnung 10/2025;-44,95\n")
                fh.write("06.10.2025;Example AI Inc;Subscription;-23,80\n")
            (t / "fmt.json").write_text('{"delimiter":";","date_col":"Buchungstag","amount_col":"Betrag",'
                                        '"counterparty_col":"Beguenstigter/Zahlungspflichtiger","purpose_col":"Verwendungszweck"}')
            (t / "rules.json").write_text('[{"match":"telekom","category":"telecom"},'
                                          '{"match":"example ai","category":"software","work_share":"1"}]')
            cmd = [sys.executable, str(SCRIPTS / "monthly_scan.py"), "--month", "2025-10", "--bank", str(t / "bank.csv"),
                   "--bank-format", str(t / "fmt.json"), "--rules", str(t / "rules.json"), "--docs", str(t / "docs"),
                   "--emails", str(t / "mail"), "--ledger", str(t / "ledger.csv"), "--out", str(t / "out")]
            subprocess.run(cmd, check=True, capture_output=True)
            report = (t / "out" / "2025-10.md").read_text(encoding="utf-8")
            self.assertIn("2 deductible candidates", report)
            self.assertIn("2025-10_telekom.txt", report)   # same amount, right month
            self.assertNotIn("2025-09_telekom.txt", report)
            self.assertIn("r.eml", report)            # email receipt matched to the bank payment
            self.assertIn("Streamco Media", report)   # recurring payment without a rule
            subprocess.run(cmd, check=True, capture_output=True)  # second run adds nothing
            with (t / "ledger.csv").open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 2)
            self.assertIn("person", rows[0])
            self.assertEqual(rows[0]["status"], "proposed")
            self.assertEqual(rows[0]["currency"], "EUR")


if __name__ == "__main__":
    unittest.main()
